"""Autostart via an XDG desktop entry.

The delay gives GNOME and KDE time to bring up their tray host; without it the
app can start before anything is listening and fall back to its retry loop.
"""

from __future__ import annotations

import shlex
from pathlib import Path

FILENAME = "tokentray.desktop"


def _entry_path() -> Path:
    import os

    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / FILENAME


def location() -> str:
    return str(_entry_path())


def is_enabled() -> bool:
    return _entry_path().exists()


def registered_command() -> list[str] | None:
    try:
        text = _entry_path().read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("Exec="):
            parts = shlex.split(line[len("Exec="):])
            return [p for p in parts if p != "--autostart"] or None
    return None


def enable(command: list[str]) -> None:
    path = _entry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    exec_line = shlex.join(command + ["--autostart"])
    path.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                "Name=tokentray",
                "Comment=Claude Code and Codex quota monitor",
                # Named, not a path: GNOME's Startup Applications list shows a
                # generic placeholder without it. Resolves once install.sh has
                # put the PNGs into hicolor, and harmlessly falls back if not.
                "Icon=io.github.messy-snail.tokentray",
                f"Exec={exec_line}",
                "Terminal=false",
                "X-GNOME-Autostart-enabled=true",
                "X-GNOME-Autostart-Delay=10",
                "",
            ]
        ),
        encoding="utf-8",
    )


def disable() -> None:
    _entry_path().unlink(missing_ok=True)
