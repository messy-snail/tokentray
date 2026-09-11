"""First-run setup, driven from the terminal.

The wizard's job is to make the common case a single confirmation: both CLIs are
usually already logged in, so detection runs first and manual entry exists only
as a fallback. It also says out loud what a pasted Claude token will and will not
do, because that is the one choice here that quietly stops working after a few
hours.
"""

from __future__ import annotations

import locale
import time
import webbrowser
from dataclasses import dataclass

import typer

from . import autostart
from .connections import INSTALL_URLS, AuthState, inspect, login_command, make_provider, observe
from .core import i18n
from .core.config import Config
from .core.models import Status
from .core.secrets import (
    CLAUDE_ACCESS_TOKEN,
    CODEX_ACCESS_TOKEN,
    CODEX_ACCOUNT_ID,
    SecretStore,
    default_store,
)
from .login_terminal import LaunchError, launch
from .setup_display import say, show_connections


@dataclass
class ProviderSetup:
    key: str
    token_name: str
    token_expires: bool


PROVIDERS = [
    ProviderSetup(
        key="claude",
        token_name=CLAUDE_ACCESS_TOKEN,
        token_expires=True,
    ),
    ProviderSetup(
        key="codex",
        token_name=CODEX_ACCESS_TOKEN,
        token_expires=False,
    ),
]


def run(config: Config, store: SecretStore | None = None, *, launch: bool = True) -> int:
    store = store or default_store()
    _choose_language(config)
    show_connections([inspect(p.key, config, store) for p in PROVIDERS], introduction=True)

    configured = 0
    for provider in PROVIDERS:
        if _configure_provider(provider, config, store):
            configured += 1
        typer.echo("")

    if configured == 0:
        say(i18n.t("connect.none"))

    _choose_autostart()
    config_path = config.save()

    typer.echo("")
    say(i18n.t("connect.done"))
    typer.echo(f"  config   {config_path}")
    typer.echo("  check    tokentray status")

    if launch and typer.confirm(i18n.t("connect.start"), default=True):
        from .app import main as gui_main

        return gui_main(autostart_launch=False)
    return 0


def _configure_provider(provider: ProviderSetup, config: Config, store: SecretStore) -> bool:
    while True:
        connection = inspect(provider.key, config, store)
        show_connections([connection])
        if connection.auth in (AuthState.FOUND, AuthState.CONNECTED):
            config.set(f"{provider.key}.enabled", True)
            return True
        if provider.token_expires:
            say(i18n.t("connect.manual"))
        choice = typer.prompt(i18n.t("connect.choice"), default="s").strip().lower()[:1]
        if choice == "r":
            continue
        if choice == "i":
            say(INSTALL_URLS[provider.key])
            webbrowser.open(INSTALL_URLS[provider.key])
            continue
        if choice == "l":
            if _login(provider.key, config, store) == Status.OK:
                config.set(f"{provider.key}.enabled", True)
                return True
            continue
        break

    if choice == "d":
        config.set(f"{provider.key}.enabled", False)
        say(i18n.t("connect.disabled"))
        return False
    if choice != "p":
        config.set(f"{provider.key}.enabled", True)
        return False

    token = typer.prompt(i18n.t("connect.token"), hide_input=True).strip()
    if not token:
        say(i18n.t("connect.empty"))
        return False
    store.set(provider.token_name, token)
    if provider.key == "codex":
        account = typer.prompt(i18n.t("connect.account"), default="").strip()
        if account:
            store.set(CODEX_ACCOUNT_ID, account)
    config.set(f"{provider.key}.enabled", True)
    say(i18n.t("connect.saved", backend=store.backend_name()))
    if store.using_fallback:
        say(i18n.t("connect.secret_fallback"))
    return True


def _choose_language(config: Config) -> None:
    codes = [code for code, _ in i18n.available_languages()]
    current = i18n.normalize(config.get("language") or locale.getlocale()[0])
    names = ", ".join(f"{code} ({name})" for code, name in i18n.available_languages())
    typer.secho("Language", bold=True)
    typer.echo(f"  available: {names}")
    chosen = typer.prompt("  language", default=current).strip().lower()
    config.set("language", chosen if chosen in codes else current)
    i18n.set_language(config.get("language"))


def _choose_autostart() -> None:
    say(i18n.t("connect.autostart"))
    already = autostart.is_enabled()
    if typer.confirm(i18n.t("connect.autostart_question"), default=not already):
        say(i18n.t("connect.enabled" if autostart.enable() else "connect.autostart_failed"))
    elif already:
        autostart.disable()
        say(i18n.t("connect.disabled"))


def _login(key: str, config: Config, store: SecretStore) -> Status | None:
    """Wait locally in the interactive wizard; only fetch when credentials change."""
    before = observe(key, config, store)
    if not before.connection.executable:
        say(i18n.t("connect.path_hint"))
        say(INSTALL_URLS[key])
        return
    try:
        launch(key, before.connection.executable)
    except LaunchError as exc:
        say(i18n.t("connect." + str(exc)))
        say(login_command(key))
        return
    say(i18n.t("connect.waiting") + " (Ctrl+C)")
    deadline = time.monotonic() + 300
    try:
        while time.monotonic() < deadline:
            time.sleep(2)
            after = observe(key, config, store)
            if after.fingerprint and after.fingerprint != before.fingerprint:
                reader = make_provider(key, config, store)
                try:
                    snapshot = reader.fetch(force=True)
                finally:
                    reader.close()
                message = "connected" if snapshot.status == Status.OK else "network"
                if snapshot.status in (Status.EXPIRED, Status.UNAUTHORIZED):
                    message = "expired"
                say(i18n.t("connect." + message))
                return snapshot.status
    except KeyboardInterrupt:
        return
    say(i18n.t("connect.timeout"))
