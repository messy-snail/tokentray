"""Rich onboarding output with plain and narrow-terminal fallbacks."""

from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .connections import Connection, NAMES
from .core.i18n import t


def console() -> Console:
    return Console(file=sys.stdout, highlight=False)


def safe(text: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding)


def say(text: str) -> None:
    console().print(Text(safe(text)))


def show_connections(connections: list[Connection], *, introduction: bool = False) -> None:
    output = console()
    if introduction:
        if output.is_terminal:
            output.print(Panel(Text(safe(t("connect.intro"))), title=safe(t("connect.title")),
                               border_style="cyan", safe_box=True))
        else:
            say(t("connect.title"))
            say(t("connect.intro"))
    headers = [t("connect." + key) for key in ("service", "cli", "auth", "next")]
    rows = [[NAMES[item.provider], t("connect.detected" if item.executable else "connect.not_found"),
             t("connect." + item.auth.value), t("connect." + item.action.value)] for item in connections]
    if not output.is_terminal or output.width < 90:
        for row in rows:
            say(row[0])
            for header, value in zip(headers[1:], row[1:]):
                say(f"  {header}: {value}")
        return
    table = Table(box=None, padding=(0, 2))
    for header in headers:
        table.add_column(safe(header), style="cyan" if header == headers[0] else None)
    for row in rows:
        table.add_row(*(Text(safe(value)) for value in row))
    output.print(table)
