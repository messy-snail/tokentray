"""The reply must survive a pipe the server closes the instant it has answered.

``_send_windows`` opens the pipe unbuffered, so the file object's own
``readline`` would ask for one byte at a time. The server writes its answer and
disconnects in the same breath, and one of those one-byte reads landing on a
pipe that is already going away failed the whole exchange - about a third of the
time when caller and server shared a process.
"""

import json

import pytest

from tokentray import ipc


class FakeHandle:
    """A pipe that hands back ``chunks``, then raises like a closed one."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read(self, size):
        if self._chunks:
            return self._chunks.pop(0)
        raise OSError(22, "Invalid argument")


def test_a_reply_split_across_reads_is_reassembled():
    reply = json.dumps({"ok": True, "pid": 4242}).encode() + b"\n"
    handle = FakeHandle([reply[:5], reply[5:]])
    assert json.loads(ipc._read_reply(handle, 2.0)) == {"ok": True, "pid": 4242}


def test_a_close_right_after_the_reply_is_not_a_failure():
    reply = json.dumps({"ok": True, "pid": 4242}).encode() + b"\n"
    # One chunk carries the whole line; the next read raises. Stopping at the
    # newline is what keeps that raise out of the result.
    handle = FakeHandle([reply])
    assert json.loads(ipc._read_reply(handle, 2.0)) == {"ok": True, "pid": 4242}


def test_a_close_before_any_reply_reads_as_nothing():
    assert ipc._read_reply(FakeHandle([]), 2.0) == b""


def test_an_answer_that_never_arrives_gives_up_at_the_timeout():
    """The timeout argument was accepted and then ignored on Windows."""
    handle = FakeHandle([b"partial"] * 10_000)
    assert ipc._read_reply(handle, 0.0) == b""


@pytest.mark.parametrize("trailing", [b"\n", b"\r\n", b"\n  "])
def test_surrounding_whitespace_is_stripped(trailing):
    handle = FakeHandle([b'{"ok": true}' + trailing])
    assert json.loads(ipc._read_reply(handle, 2.0)) == {"ok": True}
