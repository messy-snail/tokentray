"""Single-instance enforcement and a tiny command channel.

Running ``tokentray`` twice should focus the existing instance rather than put a
second icon in the tray, and ``tokentray status`` should be able to ask the
running app instead of spending a fresh API call. Both needs are served by one
local socket.

The server half needs Qt; the client half deliberately does not, so short-lived
CLI commands stay fast.
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import socket
import sys
from typing import Callable

from .core import paths

log = logging.getLogger("tokentray.ipc")

CMD_SHOW = "show"
CMD_REFRESH = "refresh"
CMD_STATUS = "status"
CMD_STOP = "stop"
CMD_TEST = "test-alert"
CMD_RELOAD_CONFIG = "reload-config"
# Two commands rather than one parameterised one: the wire format carries a bare
# string, and widening it for this would be all cost and no gain.
CMD_RESET_WELCOME = "reset-welcome"
CMD_RESET_ALERTS = "reset-alerts"

# Commands are tiny and come from our own CLI, so this only bounds a misbehaving client.
READ_TIMEOUT_MS = 500


def socket_name() -> str:
    """Address of the command channel.

    A per-user name keeps two accounts on one machine from colliding; on Unix it
    lives in the runtime directory rather than the cache, because cache cleaners
    delete sockets and a vanished socket looks like "no instance running".
    """
    if sys.platform == "win32":
        return f"tokentray-{_username()}"
    return str(paths.runtime_dir() / "tokentray.sock")


def _username() -> str:
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - unusual container setups
        return str(os.getuid()) if hasattr(os, "getuid") else "user"


# -- client (no Qt) -----------------------------------------------------------


def send_command(command: str, timeout: float = 2.0) -> dict | None:
    """Send ``command`` to a running instance. None means nothing is listening."""
    payload = (json.dumps({"cmd": command}) + "\n").encode("utf-8")
    try:
        if sys.platform == "win32":
            return _send_windows(payload, timeout)
        return _send_unix(payload, timeout)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _send_windows(payload: bytes, timeout: float) -> dict | None:
    path = rf"\\.\pipe\{socket_name()}"
    try:
        handle = open(path, "r+b", buffering=0)
    except OSError:
        return None
    with handle:
        handle.write(payload)
        handle.flush()
        raw = handle.readline()
    return json.loads(raw.decode("utf-8")) if raw else None


def _send_unix(payload: bytes, timeout: float) -> dict | None:
    path = socket_name()
    if not os.path.exists(path):
        return None
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(path)
        client.sendall(payload)
        chunks: list[bytes] = []
        while b"\n" not in b"".join(chunks):
            chunk = client.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        client.close()
    raw = b"".join(chunks).strip()
    return json.loads(raw.decode("utf-8")) if raw else None


def is_running() -> bool:
    return send_command(CMD_STATUS) is not None


# -- server (Qt) --------------------------------------------------------------


class SingleInstance:
    """Owns the lock and the listening socket for the running instance."""

    def __init__(self, handler: Callable[[str], dict]) -> None:
        from PySide6.QtCore import QLockFile

        self._handler = handler
        self._server = None
        self._lock = QLockFile(str(paths.lock_file()))
        # A crashed instance leaves the lock behind; treat any lock whose owner
        # is gone as free rather than refusing to start forever.
        self._lock.setStaleLockTime(30_000)

    def acquire(self) -> bool:
        """True when this process is now the primary instance."""
        from PySide6.QtNetwork import QLocalServer

        # Ask first: if something answers, it owns the tray and we should not.
        if send_command(CMD_STATUS) is not None:
            return False
        if not self._lock.tryLock(100):
            return False

        name = socket_name()
        QLocalServer.removeServer(name)  # clear a socket left by a crash
        server = QLocalServer()
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(name):
            log.warning("could not listen on %s: %s", name, server.errorString())
            self._lock.unlock()
            return False

        server.newConnection.connect(self._on_connection)
        self._server = server
        return True

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        self._lock.unlock()

    def _on_connection(self) -> None:
        """Read one command, answer it, and close.

        Handled synchronously rather than through a readyRead callback: the
        socket is owned by C++, and a deferred callback can run after Qt has
        already destroyed it ("Internal C++ object already deleted"). Commands
        are a few bytes from our own CLI, so the wait is immeasurable.
        """
        if self._server is None:
            return
        connection = self._server.nextPendingConnection()
        if connection is None:
            return
        try:
            # Data may already be buffered before newConnection is delivered.
            # Waiting for another arrival then times out on a complete command.
            if connection.bytesAvailable() == 0 and not connection.waitForReadyRead(READ_TIMEOUT_MS):
                return
            raw = bytes(connection.readAll()).decode("utf-8", "replace").strip()
            if not raw:
                return
            try:
                command = json.loads(raw).get("cmd", "")
            except json.JSONDecodeError:
                command = ""
            try:
                response = self._handler(command)
            except Exception as exc:  # never let a bad command kill the app
                log.exception("IPC handler failed")
                response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            connection.write((json.dumps(response) + "\n").encode("utf-8"))
            connection.flush()
            connection.waitForBytesWritten(READ_TIMEOUT_MS)
        except Exception:
            log.exception("IPC connection failed")
        finally:
            try:
                connection.disconnectFromServer()
                connection.deleteLater()
            except RuntimeError:
                pass  # already gone; nothing to clean up
