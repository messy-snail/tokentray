"""Start-at-login registration.

Every backend registers the same thing: the *GUI* entry point, never the console
one. On Windows that is the difference between a silent start and a console
window flashing up at every login.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_ID = "io.github.messy-snail.tokentray"
ENTRY = "tokentray-gui"


def gui_command() -> list[str]:
    """The command an OS should run at login, as an argv list.

    Three shapes to cover: a PyInstaller bundle (a sibling executable), a
    ``uv tool``/pipx install (a shim on PATH), and a development checkout
    (``pythonw -m tokentray``).
    """
    if getattr(sys, "frozen", False):
        directory = Path(sys.executable).parent
        sibling = directory / (f"{ENTRY}.exe" if os.name == "nt" else ENTRY)
        return [str(sibling if sibling.exists() else Path(sys.executable))]

    shim = shutil.which(ENTRY)
    if shim:
        return [shim]

    if os.name == "nt":
        # pythonw keeps the console from appearing; python.exe would flash one.
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        interpreter = str(pythonw if pythonw.exists() else sys.executable)
    else:
        interpreter = sys.executable
    return [interpreter, "-m", "tokentray"]


def _backend():
    if sys.platform == "win32":
        from . import windows

        return windows
    if sys.platform == "darwin":
        from . import macos

        return macos
    from . import linux

    return linux


def is_enabled() -> bool:
    try:
        return _backend().is_enabled()
    except Exception:
        return False


def enable() -> bool:
    try:
        _backend().enable(gui_command())
        return True
    except Exception:
        return False


def disable() -> bool:
    try:
        _backend().disable()
        return True
    except Exception:
        return False


def describe() -> str:
    try:
        backend = _backend()
        return f"{'enabled' if backend.is_enabled() else 'disabled'} ({backend.location()})"
    except Exception as exc:
        return f"unavailable ({type(exc).__name__})"


def repair() -> None:
    """Re-point an existing registration whose command has gone stale.

    An upgrade, a moved virtualenv or a reinstall can leave a login entry that
    launches nothing. Re-registering on every GUI start keeps it valid.
    """
    try:
        backend = _backend()
        if backend.is_enabled() and backend.registered_command() != gui_command():
            backend.enable(gui_command())
    except Exception:
        pass
