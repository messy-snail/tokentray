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
) -> None:
    """Start the tray application (same as running `tokentray` with no arguments)."""
    raise typer.Exit(_launch_gui(autostart=autostart))


@app.command()
def status(
    refresh: bool = typer.Option(False, "--refresh", help="Bypass the cache and fetch now."),
) -> None:
    """Print current quota for every configured provider."""
    config = Config.load()
    i18n.set_language(config.language)
    views = _collect_views(config, force=refresh)
    for line in _format_status(views):
        typer.echo(line)
    if not any(view.rows for view in views):
        raise typer.Exit(1)


@app.command()
def doctor() -> None:
    """Check credentials, storage and display prerequisites."""
    config = Config.load()
    i18n.set_language(config.language)
    for line in _diagnose(config):
        typer.echo(line)


@config_app.command("get")
def config_get(key: Optional[str] = typer.Argument(None)) -> None:
    """Show one value, or the whole configuration when no key is given."""
    config = Config.load()
    if key is None:
        for dotted, value in sorted(_flatten(config.as_dict())):
            typer.echo(f"{dotted} = {value!r}")
        return
    value = config.get(key, _MISSING)
    if value is _MISSING:
        typer.secho(f"unknown key: {key}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.echo(repr(value))


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    """Set a value, e.g. `tokentray config set poll_interval 300`."""
    config = Config.load()
    if config.get(key, _MISSING) is _MISSING:
        typer.secho(f"unknown key: {key}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    parsed = parse_value(value)
    config.set(key, parsed)
    path = config.save()
    typer.echo(f"{key} = {parsed!r}  ({path})")


@config_app.command("path")
def config_path() -> None:
    """Print the location of every file tokentray writes."""
    from .core import paths

    typer.echo(f"config  {paths.config_file()}")
    typer.echo(f"state   {paths.state_file()}")
    typer.echo(f"cache   {paths.cache_dir()}")
    typer.echo(f"log     {paths.log_file()}")


# -- internals ----------------------------------------------------------------

_MISSING = object()


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


def _diagnose(config: Config) -> list[str]:
    from .core import paths
    from .core.secrets import default_store
    from .providers.claude import credentials_path
    from .providers.codex import auth_path

    lines = [f"tokentray {__version__}  (python {sys.version.split()[0]}, {sys.platform})"]

    claude_file = credentials_path()
    lines.append(f"claude credentials  {_credential_state(claude_file, 'claude')}  {claude_file}")
    if sys.platform == "darwin":
        lines.append("                    (falls back to the macOS login keychain)")
    codex_file = auth_path()
    lines.append(f"codex credentials   {_credential_state(codex_file, 'codex')}  {codex_file}")

    lines.append(f"secret backend      {default_store().backend_name()}")
    lines.append(f"config              {paths.config_file()}")
    lines.append(f"poll interval       {config.poll_interval}s (cache ttl {config.cache_ttl}s)")
    lines.append(f"language            {config.language}")
    lines.append(f"thresholds          {config.thresholds}")
    lines.append(f"remind before       {config.remind_before or 'off'}")
    lines.append(f"tray                {_tray_report()}")
    return lines



def _credential_state(path, provider: str) -> str:
    """Distinguish "no file", "file but no token", and "usable".

    The empty-token case is real: Claude Code writes the file with plan metadata
    but leaves accessToken blank when the session is authenticated elsewhere
    (for example through the desktop app), and "missing" would be misleading.
    """
    import json

    if not path.exists():
        return "missing"
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return "unreadable"
    if provider == "claude":
        token = (data.get("claudeAiOauth") or {}).get("accessToken")
    else:
        token = (data.get("tokens") or {}).get("access_token")
    if not token:
        return "no token in file"
    return "found"


def _tray_report() -> str:
    """Report tray availability without leaving a QApplication behind."""
    try:
        from PySide6.QtWidgets import QApplication, QSystemTrayIcon
    except Exception as exc:  # pragma: no cover - depends on the install
        return f"PySide6 unavailable ({type(exc).__name__})"
    # A QApplication is required before querying tray availability. This process
    # exits right after, so there is nothing to tear down.
    qapp = QApplication.instance() or QApplication([])
    available = QSystemTrayIcon.isSystemTrayAvailable()
    return f"{'available' if available else 'NOT available'} (platform: {qapp.platformName()})"


def _flatten(data: dict, prefix: str = "") -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    for key, value in data.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            out.extend(_flatten(value, f"{dotted}."))
        else:
            out.append((dotted, value))
    return out


def _launch_gui(*, autostart: bool) -> int:
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
