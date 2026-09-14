"""Command-line interface.

The bare ``tokentray`` command starts the tray app; every other subcommand is a
short-lived process that either talks to a running instance over IPC or does its
work directly. Qt is imported only on the paths that actually need it, so
``tokentray status`` stays fast on a machine with no display.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional

import typer

from . import __version__
from .core import compute, i18n
from .core.cache import Cache
from .core.config import Config, parse_value
from .core.view import ProviderView, build_view

app = typer.Typer(
    name="tokentray",
    help="System-tray monitor for Claude Code and OpenAI Codex quota.",
    no_args_is_help=False,
    add_completion=False,
)
config_app = typer.Typer(help="Read and write configuration values.")
app.add_typer(config_app, name="config")
autostart_app = typer.Typer(help="Manage starting tokentray at login.")
app.add_typer(autostart_app, name="autostart")
webhook_app = typer.Typer(help="Configure one outbound notification destination.")
app.add_typer(webhook_app, name="webhook")
state_app = typer.Typer(help="Reset the bookkeeping tokentray keeps between runs.")
app.add_typer(state_app, name="state")


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
    autostart: bool = typer.Option(
        False, "--autostart", hidden=True, help="Started by the OS at login."
    ),
) -> None:
    if version:
        typer.echo(f"tokentray {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        raise typer.Exit(_launch_gui(autostart=autostart))


@app.command()
def run(
    autostart: bool = typer.Option(False, "--autostart", hidden=True),
    foreground: bool = typer.Option(
        False, "--foreground", help="Keep the app attached to this terminal for debugging.",
    ),
) -> None:
    """Start the tray application (same as running `tokentray` with no arguments)."""
    raise typer.Exit(_launch_gui(autostart=autostart, foreground=foreground))


@app.command()
def status(
    refresh: bool = typer.Option(False, "--refresh", help="Bypass the cache and fetch now."),
    local: bool = typer.Option(False, "--local", help="Always fetch here, ignoring a running app."),
) -> None:
    """Print current quota for every configured provider."""
    from . import ipc

    config = Config.load()
    i18n.set_language(config.language)

    if not local:
        # Ask the running instance first: it already has fresh data, and a second
        # fetch would spend a request to learn the same thing.
        remote = ipc.send_command(ipc.CMD_REFRESH if refresh else ipc.CMD_STATUS)
        if remote is not None and remote.get("ok"):
            for line in _format_remote(remote):
                echo(line)
            return

    views = _collect_views(config, force=refresh)
    for line in _format_status(views):
        echo(line)
    if not any(view.rows for view in views):
        raise typer.Exit(1)


@app.command()
def setup() -> None:
    """Interactive first-run configuration."""
    from .setup_wizard import run as run_wizard

    config = Config.load()
    i18n.set_language(config.language)
    raise typer.Exit(run_wizard(config))


@app.command("open")
def open_panel() -> None:
    """Show the detail panel of the running app."""
    _require_running(ipc_command="show")


@app.command("refresh")
def refresh_now() -> None:
    """Ask the running app to fetch fresh data."""
    _require_running(ipc_command="refresh")


@app.command("stop")
def stop() -> None:
    """Quit the running app."""
    _require_running(ipc_command="stop", quiet=True)
    typer.echo("stopped")


@app.command()
def doctor() -> None:
    """Check credentials, storage, display and notification delivery."""
    from .diagnostics import report

    config = Config.load()
    i18n.set_language(config.language)
    for line in report(config):
        echo(line)


@config_app.command("get")
def config_get(key: Optional[str] = typer.Argument(None)) -> None:
    """Show one value, or the whole configuration when no key is given."""
    config = Config.load()
    if key is None:
        for dotted, value in sorted(_flatten(config.as_dict())):
            typer.echo(f"{dotted} = {_config_repr(dotted, value)}")
        return
    value = config.get(key, _MISSING)
    if value is _MISSING:
        typer.secho(f"unknown key: {key}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.echo(_config_repr(key, value))


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    """Set a value, e.g. `tokentray config set poll_interval 300`."""
    config = Config.load()
    if config.get(key, _MISSING) is _MISSING:
        typer.secho(f"unknown key: {key}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if key == "webhook.url":
        from .notify.configuration import save_destination

        save_destination(
            config,
            enabled=bool(config.get("webhook.enabled", False)),
            kind=str(config.get("webhook.kind", "generic")),
            url=value,
        )
        _reload_running_config()
        from .core import paths

        typer.echo(f"webhook.url = '********'  ({paths.config_file()})")
        return
    parsed = parse_value(value)
    config.set(key, parsed)
    path = config.save()
    # Without this a running instance keeps the value it started with, which is
    # how `native_notifications = false` used to need a restart to mean anything.
    _reload_running_config()
    typer.echo(f"{key} = {parsed!r}  ({path})")


@autostart_app.command("enable")
def autostart_enable() -> None:
    """Start tokentray automatically at login."""
    from . import autostart as auto

    if not auto.enable():
        typer.secho("could not enable autostart", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.echo(f"enabled: {' '.join(auto.gui_command())}")


@autostart_app.command("disable")
def autostart_disable() -> None:
    """Stop launching tokentray at login."""
    from . import autostart as auto

    auto.disable()
    typer.echo("disabled")


@autostart_app.command("status")
def autostart_status() -> None:
    """Report whether tokentray is registered to start at login."""
    from . import autostart as auto

    typer.echo(auto.describe())
    typer.echo(f"command: {' '.join(auto.gui_command())}")


@config_app.command("path")
def config_path() -> None:
    """Print the location of every file tokentray writes."""
    from .core import paths

    typer.echo(f"config  {paths.config_file()}")
    typer.echo(f"state   {paths.state_file()}")
    typer.echo(f"cache   {paths.cache_dir()}")
    typer.echo(f"log     {paths.log_file()}")


@state_app.command("reset")
def state_reset(
    welcome: bool = typer.Option(
        False, "--welcome", help="Show the first-run welcome again on the next start."
    ),
    alerts: bool = typer.Option(
        False, "--alerts", help="Forget which thresholds and reminders already fired."
    ),
    everything: bool = typer.Option(False, "--all", help="Both of the above."),
) -> None:
    """Clear remembered bookkeeping so a one-time notice or alert can happen again."""
    from . import ipc
    from .core import paths, state

    if everything:
        welcome = alerts = True
    if not (welcome or alerts):
        typer.secho(
            "nothing to reset - pass --welcome, --alerts or --all",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(1)

    # A running app holds the state in memory and rewrites the whole file on every
    # poll, so writing the file underneath it would be undone within one interval.
    # Probing separately rather than inferring liveness from the first reset keeps
    # --all from half-applying if the app quits mid-sequence, and the reply carries
    # the pause flag needed below.
    live = ipc.send_command(ipc.CMD_STATUS)
    if live is not None:
        if welcome:
            ipc.send_command(ipc.CMD_RESET_WELCOME)
        if alerts:
            ipc.send_command(ipc.CMD_RESET_ALERTS)
        target = "the running app"
    else:
        data = state.load()
        if welcome:
            state.clear_welcome(data)
        if alerts:
            state.clear_alerts(data)
        state.save(data)
        target = str(paths.state_file())

    cleared = " and ".join(n for n, on in (("welcome", welcome), ("alerts", alerts)) if on)
    echo(f"reset {cleared} ({target})")
    if welcome:
        echo("the welcome notice will appear the next time tokentray starts")
    if alerts and live is not None and live.get("paused"):
        echo("note: alerts are paused; resume them from the tray menu to see any")


@webhook_app.command("setup")
def webhook_setup(
    service: str = typer.Option("slack", "--service", "-s", help="slack, discord, ntfy, or generic"),
    url: Optional[str] = typer.Option(None, "--url", help="Webhook URL (prompted securely when omitted)."),
    disabled: bool = typer.Option(False, "--disabled", help="Save the destination without enabling it."),
) -> None:
    """Save a webhook URL in the OS keyring and apply it to the running app."""
    from .notify.configuration import save_destination

    value = url if url is not None else typer.prompt("Webhook URL", hide_input=True)
    config = Config.load()
    try:
        settings = save_destination(
            config, enabled=not disabled, kind=service.lower(), url=value
        )
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    _reload_running_config()
    typer.echo(f"{settings.kind} webhook {'enabled' if settings.enabled else 'saved'}")


@webhook_app.command("test")
def webhook_test() -> None:
    """Send one test message to the configured destination."""
    from .core.alerts import AlertEvent
    from .notify.webhook import Webhook

    hook = Webhook.from_config(Config.load())
    result = hook.deliver(
        AlertEvent(kind="info", key="test", title="tokentray", body="Webhook notifications are working.")
    )
    if not result.ok:
        typer.secho(f"delivery failed: {result.error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.echo("test notification sent")


# -- internals ----------------------------------------------------------------

# The status output uses emoji and box-drawing characters. A Korean Windows
# console is cp949 and a Japanese one cp932; writing an unencodable character
# there raises UnicodeEncodeError and kills the command. Substitute rather than
# crash, and keep the meaning: the tier marker is the point, not the emoji.
_FALLBACKS = {
    "🟢": "[ok]", "🟡": "[! ]", "🔴": "[!!]",
    "🔥": "(hot)", "⚡": "(fast)", "✅": "(ok)", "🐢": "(slow)",
    "■": "#", "□": ".", "·": "-", "—": "-", "…": "...",
    "✓": "*", "×": "x",
}


def _console_safe(text: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
        return text
    except (UnicodeEncodeError, LookupError):
        pass
    out = []
    for char in text:
        try:
            char.encode(encoding)
            out.append(char)
        except (UnicodeEncodeError, LookupError):
            out.append(_FALLBACKS.get(char, "?"))
    return "".join(out)


def echo(text: str = "") -> None:
    typer.echo(_console_safe(text))



_MISSING = object()


def _config_repr(key: str, value: object) -> str:
    if key == "webhook.url" and value:
        return repr("********")
    return repr(value)


def _reload_running_config() -> None:
    """Let a running instance pick up a setting that does not need a restart."""
    from . import ipc

    ipc.send_command(ipc.CMD_RELOAD_CONFIG)


def _collect_views(config: Config, *, force: bool) -> list[ProviderView]:
    from .providers import build_providers

    now = datetime.now(timezone.utc)
    views: list[ProviderView] = []
    for provider in build_providers(config, Cache()):
        try:
            snapshot = provider.fetch(force=force)
        finally:
            provider.close()
        views.append(build_view(snapshot, now))
    return views


def _format_status(views: list[ProviderView]) -> list[str]:
    lines: list[str] = []
    for view in views:
        if lines:
            lines.append("")
        lines.append(view.title)
        lines.append("-" * max(len(view.title), 24))
        if view.message:
            lines.append(f"  {view.message}")
        for row in view.rows:
            emoji = compute.TIER_EMOJI[row.tier]
            lines.append(f"  {emoji} {row.label}: {row.remaining_text}")
            lines.append(f"     {row.bar}")
            detail = "  ".join(x for x in (row.refills, row.burns) if x)
            if detail:
                lines.append(f"     {detail}")
            if row.pace:
                lines.append(f"     {row.pace} {row.pace_icon}".rstrip())
        for note in view.notes:
            lines.append(f"  {note}")
        if view.source:
            lines.append(f"  {i18n.t('label.source')}: {view.source}")
    return lines or ["no providers enabled"]


def _require_running(*, ipc_command: str, quiet: bool = False) -> None:
    from . import ipc

    if ipc.send_command(ipc_command) is None:
        typer.secho(
            "tokentray is not running - start it with `tokentray`",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(1)
    if not quiet:
        typer.echo("ok")


def _format_remote(payload: dict) -> list[str]:
    """Render the snapshot a running instance reported over IPC."""
    lines: list[str] = []
    for provider in payload.get("providers", []):
        if lines:
            lines.append("")
        title = str(provider.get("title", ""))
        lines.append(title)
        lines.append("-" * max(len(title), 24))
        if provider.get("message"):
            lines.append(f"  {provider['message']}")
        for window in provider.get("windows", []):
            emoji = compute.TIER_EMOJI.get(window.get("tier", "green"), "")
            lines.append(f"  {emoji} {window.get('label')}: {window.get('text')}")
            lines.append(f"     {compute.progress_bar(float(window.get('remaining', 0)))}")
            detail = "  ".join(x for x in (window.get("refills"), window.get("burns")) if x)
            if detail:
                lines.append(f"     {detail}")
            if window.get("pace"):
                lines.append(f"     {window['pace']}")
        for note in provider.get("notes", []):
            lines.append(f"  {note}")
        if provider.get("source"):
            lines.append(f"  {i18n.t('label.source')}: {provider['source']}")
    footer = f"(from the running app, pid {payload.get('pid')})"
    if payload.get("paused"):
        footer = f"(from the running app, pid {payload.get('pid')}; alerts paused)"
    lines.append("")
    lines.append(footer)
    return lines or ["no providers enabled"]


def _flatten(data: dict, prefix: str = "") -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    for key, value in data.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            out.extend(_flatten(value, f"{dotted}."))
        else:
            out.append((dotted, value))
    return out


def _launch_gui(*, autostart: bool, foreground: bool = False) -> int:
    if not foreground:
        from .launcher import start

        return start(autostart=autostart)
    try:
        from .app import main as gui_main
    except ImportError as exc:  # pragma: no cover - only without PySide6
        typer.secho(f"GUI unavailable: {exc}", fg=typer.colors.RED, err=True)
        return 1
    return gui_main(autostart=autostart)


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
