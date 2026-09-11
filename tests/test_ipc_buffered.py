"""A buffered command must not wait for a second readyRead notification."""

import json
from types import SimpleNamespace

from tokentray import ipc


def test_already_buffered_command_is_answered():
    payload = json.dumps({"cmd": ipc.CMD_STATUS}).encode() + b"\n"
    replies = []

    def unexpected_wait(timeout):
        raise AssertionError("The complete command has already arrived")

    connection = SimpleNamespace(
        bytesAvailable=lambda: len(payload), waitForReadyRead=unexpected_wait,
        readAll=lambda: payload, write=replies.append, flush=lambda: None,
        waitForBytesWritten=lambda timeout: True,
        disconnectFromServer=lambda: None, deleteLater=lambda: None,
    )
    instance = object.__new__(ipc.SingleInstance)
    instance._server = SimpleNamespace(nextPendingConnection=lambda: connection)
    instance._handler = lambda command: {"ok": True, "echo": command}
    instance._on_connection()
    assert len(replies) == 1
    assert json.loads(replies[0]) == {"ok": True, "echo": ipc.CMD_STATUS}
