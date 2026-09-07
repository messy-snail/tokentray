"""First-run setup, driven from the terminal.

The wizard's job is to make the common case a single confirmation: both CLIs are
usually already logged in, so detection runs first and manual entry exists only
as a fallback. It also says out loud what a pasted Claude token will and will not
do, because that is the one choice here that quietly stops working after a few
hours.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

import typer

from . import autostart
from .core import i18n
from .core.config import Config
from .core.secrets import (
    CLAUDE_ACCESS_TOKEN,
    CODEX_ACCESS_TOKEN,
    CODEX_ACCOUNT_ID,
    SecretStore,
    default_store,
)


@dataclass
class ProviderSetup:
    key: str
    name: str
    cli: str
    login_hint: str
    detect: Callable[[], tuple[bool, str]]
    token_name: str
    token_expires: bool


def _detect_claude() -> tuple[bool, str]:
    from .providers.claude import credentials_path

    path = credentials_path()
    if not path.exists():
        return False, f"no credential file at {path}"
    from .providers.claude import _from_file

    creds = _from_file(path)
    if creds is None:
        if sys.platform == "darwin":
            return False, f"{path} has no usable token (will also try the login keychain)"
        return False, f"{path} exists but holds no access token"
    return True, f"found in {path}"


def _detect_codex() -> tuple[bool, str]:
    from .providers.codex import _from_file, auth_path

    path = auth_path()
    if not path.exists():
        return False, f"no credential file at {path}"
    if _from_file(path) is None:
        return False, f"{path} is in API-key mode, which the usage endpoint cannot use"
    return True, f"found in {path}"


PROVIDERS = [
    ProviderSetup(
        key="claude",
        name="Claude Code",
        cli="claude",
        login_hint="run `claude` in a terminal and sign in",
        detect=_detect_claude,
        token_name=CLAUDE_ACCESS_TOKEN,
        token_expires=True,
    ),
    ProviderSetup(
        key="codex",
        name="Codex",
        cli="codex",
        login_hint="run `codex` in a terminal and sign in",
        detect=_detect_codex,
        token_name=CODEX_ACCESS_TOKEN,
        token_expires=False,
    ),
]


def run(config: Config, store: SecretStore | None = None, *, launch: bool = True) -> int:
    store = store or default_store()
    typer.secho("tokentray setup", bold=True)
    typer.echo("")

    configured = 0
    for provider in PROVIDERS:
        if _configure_provider(provider, config, store):
            configured += 1
        typer.echo("")

    if configured == 0:
        typer.secho(
            "No provider is set up yet. tokentray will keep checking, and will pick "
            "them up as soon as you sign in to either CLI.",
            fg=typer.colors.YELLOW,
        )
        typer.echo("")

    _choose_language(config)
    _choose_autostart()
    config_path = config.save()

    typer.echo("")
    typer.secho("Done.", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  config   {config_path}")
    typer.echo("  check    tokentray status")

    if launch and typer.confirm("Start tokentray now?", default=True):
        from .app import main as gui_main

        return gui_main(autostart_launch=False)
    return 0


def _configure_provider(provider: ProviderSetup, config: Config, store: SecretStore) -> bool:
    typer.secho(provider.name, bold=True)
    detected, detail = provider.detect()

    if detected:
        typer.secho(f"  detected - {detail}", fg=typer.colors.GREEN)
        config.set(f"{provider.key}.enabled", True)
        return True

    typer.secho(f"  not detected - {detail}", fg=typer.colors.YELLOW)
    typer.echo(f"  Best fix: {provider.login_hint}, then re-run this wizard.")

    if provider.token_expires:
        # Saying this up front is the whole point: a pasted Claude token buys a
        # few hours, and the user should know that before choosing it.
        typer.echo(
            "  A pasted token also works, but Claude's expires within hours and only\n"
            "  Claude Code can refresh it, so you would have to paste a new one each time."
        )

    choice = typer.prompt(
        "  [s]kip for now, [p]aste a token, or [d]isable this provider",
        default="s",
        show_default=True,
    ).strip().lower()[:1]

    if choice == "d":
        config.set(f"{provider.key}.enabled", False)
        typer.echo("  disabled.")
        return False
    if choice != "p":
        config.set(f"{provider.key}.enabled", True)
        return False

    token = typer.prompt("  access token", hide_input=True).strip()
    if not token:
        typer.echo("  nothing entered; skipping.")
        return False
    store.set(provider.token_name, token)
    if provider.key == "codex":
        account = typer.prompt("  ChatGPT account id (optional)", default="").strip()
        if account:
            store.set(CODEX_ACCOUNT_ID, account)
    config.set(f"{provider.key}.enabled", True)
    typer.secho(f"  saved to {store.backend_name()}", fg=typer.colors.GREEN)
    if store.using_fallback:
        typer.secho(
            "  No system keyring is available, so this is an owner-readable file.",
            fg=typer.colors.YELLOW,
        )
    return True


def _choose_language(config: Config) -> None:
    codes = [code for code, _ in i18n.available_languages()]
    current = i18n.normalize(config.get("language"))
    names = ", ".join(f"{code} ({name})" for code, name in i18n.available_languages())
    typer.secho("Language", bold=True)
    typer.echo(f"  available: {names}")
    chosen = typer.prompt("  language", default=current).strip().lower()
    config.set("language", chosen if chosen in codes else current)
    i18n.set_language(config.get("language"))


def _choose_autostart() -> None:
    typer.secho("Start at login", bold=True)
    already = autostart.is_enabled()
    if typer.confirm("  Start tokentray automatically when you log in?", default=not already):
        typer.echo("  enabled." if autostart.enable() else "  could not enable (see the log).")
    elif already:
        autostart.disable()
        typer.echo("  disabled.")
