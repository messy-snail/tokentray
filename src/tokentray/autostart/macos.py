"""Autostart via a LaunchAgent.

KeepAlive is set to restart only on abnormal exit, so quitting from the tray
menu stays quit instead of respawning a second later.
"""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

LABEL = "io.github.messy-snail.tokentray"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def location() -> str:
    return str(_plist_path())


def is_enabled() -> bool:
    return _plist_path().exists()


def registered_command() -> list[str] | None:
    try:
        with _plist_path().open("rb") as fh:
            data = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException):
        return None
    args = data.get("ProgramArguments")
    if not isinstance(args, list):
        return None
    return [a for a in args if a != "--autostart"] or None


def enable(command: list[str]) -> None:
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": command + ["--autostart"],
        "RunAtLoad": True,
        # Restart if it crashes, but honour a clean quit.
        "KeepAlive": {"SuccessfulExit": False},
        "ProcessType": "Interactive",
    }
    with path.open("wb") as fh:
        plistlib.dump(payload, fh)
    _launchctl("bootstrap", f"gui/{_uid()}", str(path))


def disable() -> None:
    path = _plist_path()
    if path.exists():
        _launchctl("bootout", f"gui/{_uid()}/{LABEL}")
        path.unlink(missing_ok=True)


def _uid() -> int:
    import os

    return os.getuid()


def _launchctl(*args: str) -> None:
    # Already-loaded and not-loaded are both fine; the plist is the source of truth.
    subprocess.run(["launchctl", *args], capture_output=True, check=False, timeout=10)
