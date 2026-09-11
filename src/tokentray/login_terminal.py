"""Launch interactive login in a visible, user-owned terminal."""

from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .connections import LOGIN_ARGS


class LaunchError(Exception):
    """A terminal or provider executable could not be started."""


def terminal_command(provider: str, executable: Path) -> list[str]:
    """Build platform-specific argv; provider paths are data, never shell code."""
    argv = [str(executable), *LOGIN_ARGS[provider]]
    if sys.platform == "win32":
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            raise LaunchError("terminal_missing")
        quoted = " ".join("'" + arg.replace("'", "''") + "'" for arg in argv)
        script = "& " + quoted
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return [shell, "-NoLogo", "-NoProfile", "-NoExit", "-EncodedCommand", encoded]
    command = shlex.join(argv)
    if sys.platform == "darwin":
        # Terminal is an existing app, so explicitly carry our credential overrides.
        env = [f"{key}={os.environ[key]}" for key in ("CLAUDE_CONFIG_DIR", "CODEX_HOME")
               if key in os.environ]
        command = shlex.join(["/usr/bin/env", *env, *argv])
        literal = json.dumps(command, ensure_ascii=False)
        return ["/usr/bin/osascript", "-e", 'tell application "Terminal"', "-e", "activate",
                "-e", f"do script {literal}", "-e", "end tell"]
    for name in ("x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"):
        terminal = shutil.which(name)
        if terminal:
            # Keep output visible on command failure; no tokens occur in the script.
            shell_args = ["/bin/sh", "-c", command + "; printf '\\nPress Enter to close'; read reply"]
            if name == "xfce4-terminal":
                return [terminal, "--disable-server", "--command", shlex.join(shell_args)]
            flags = {"gnome-terminal": ["--wait", "--"], "konsole": ["--separate", "-e"]}
            return [terminal, *flags.get(name, ["-e"]), *shell_args]
    raise LaunchError("terminal_missing")


def launch(provider: str, executable: Path) -> None:
    """Open a terminal without capturing login URLs or authentication output."""
    command = terminal_command(provider, executable)
    try:
        if sys.platform == "darwin":
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=10, check=False)
            if result.returncode:
                raise LaunchError("terminal_failed")
        else:
            flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            proc = subprocess.Popen(command, cwd=Path.home(), creationflags=flags,
                                    start_new_session=sys.platform != "win32")
            # Immediate launcher errors should not look like a successful login launch.
            try:
                if proc.wait(timeout=0.2) != 0:
                    raise LaunchError("terminal_failed")
            except subprocess.TimeoutExpired:
                pass
    except (OSError, subprocess.SubprocessError) as exc:
        raise LaunchError("terminal_failed") from exc
