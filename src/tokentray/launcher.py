"""Start the GUI independently of the invoking terminal, using this installation."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from . import ipc
from .core import i18n, paths
from .core.config import Config


def gui_command() -> list[str]:
    if getattr(sys, "frozen", False):
        name = "tokentray-gui.exe" if sys.platform == "win32" else "tokentray-gui"
        executable = Path(sys.executable).with_name(name)
        if not executable.is_file():
            raise FileNotFoundError(name)
        return [str(executable)]
    interpreter = Path(sys.executable)
    if sys.platform == "win32":
        windowed = interpreter.with_name("pythonw.exe")
        if windowed.is_file():
            interpreter = windowed
    return [str(interpreter), "-m", "tokentray.app"]


def start(*, autostart: bool = False) -> int:
    from .cli import echo

    i18n.set_language(Config.load().language)
    command = ipc.CMD_STATUS if autostart else ipc.CMD_SHOW
    reply = ipc.send_command(command, timeout=0.5)
    if reply is not None and reply.get("ok"):
        echo(i18n.t("launch.already_running", pid=reply.get("pid", "?")))
        return 0

    startup_log = paths.log_dir() / "startup.log"
    try:
        args = gui_command()
        if autostart:
            args.append("--autostart")
        options: dict = {"stdin": subprocess.DEVNULL, "close_fds": True}
        if sys.platform == "win32":
            options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        # Separate from the rotating application log: an inherited open stream
        # would prevent Windows from renaming that file during log rotation.
        with startup_log.open("ab") as output:
            child = subprocess.Popen(args, stdout=output, stderr=subprocess.STDOUT, **options)
    except OSError as exc:
        echo(i18n.t("launch.failed", error=type(exc).__name__, path=startup_log))
        return 1

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        reply = ipc.send_command(ipc.CMD_STATUS, timeout=0.5)
        if reply is not None and reply.get("ok"):
            echo(i18n.t("launch.background_started"))
            return 0
        if child.poll() is not None:
            echo(i18n.t("launch.failed", error=f"exit {child.returncode}", path=startup_log))
            return 1
        time.sleep(0.1)
    echo(i18n.t("launch.pending", path=startup_log))
    return 0
