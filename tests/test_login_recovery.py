from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tokentray import login_recovery as recovery
from tokentray.connections import Action, AuthState, Connection, Observation
from tokentray.core.config import Config
from tokentray.core.models import Status
from tokentray.login_terminal import LaunchError


@pytest.fixture
def rig(qapp, monkeypatch):
    state = {"fingerprint": "before", "executable": Path("/test/cli")}
    calls, refreshed = [], []
    def observe(key, config):
        return Observation(Connection(key, state["executable"], "file", AuthState.FOUND), state["fingerprint"])
    monkeypatch.setattr(recovery, "observe", observe)
    monkeypatch.setattr(recovery, "launch", lambda key, path: calls.append((key, path)))
    manager = recovery.LoginRecovery(Config({}), lambda: refreshed.append(True))
    manager.start()
    yield manager, state, calls, refreshed
    manager.close()
    manager._pool.shutdown(wait=True)


def idle(qtbot, manager):
    qtbot.waitUntil(lambda: not manager._jobs, timeout=3000)


def view(status):
    return SimpleNamespace(provider="claude", status=status)


def test_login_dedup_and_local_change_refresh(rig, qtbot):
    manager, state, calls, refreshed = rig
    idle(qtbot, manager)
    manager.activate("claude", Action.LOGIN)
    manager.activate("claude", Action.LOGIN)
    idle(qtbot, manager)
    assert len(calls) == 1
    assert manager.sessions["claude"].waiting
    manager._submit("claude", "probe")
    idle(qtbot, manager)
    assert refreshed == []
    state["fingerprint"] = "after"
    manager._submit("claude", "probe")
    idle(qtbot, manager)
    assert refreshed == [True]
    manager.on_views([view(Status.OK)])
    assert not manager.sessions["claude"].waiting
    assert manager.sessions["claude"].connection.auth == AuthState.CONNECTED


def test_network_failure_does_not_become_expiry(rig, qtbot):
    manager, state, calls, refreshed = rig
    idle(qtbot, manager)
    manager.activate("claude", Action.LOGIN)
    idle(qtbot, manager)
    manager.sessions["claude"].changed = True
    manager.on_views([view(Status.RATE_LIMITED)])
    assert manager.sessions["claude"].message == "network"
    assert manager.sessions["claude"].connection.auth != AuthState.EXPIRED


def test_cli_rechecked_before_launch(rig, qtbot):
    manager, state, calls, refreshed = rig
    idle(qtbot, manager)
    state["executable"] = None
    manager.activate("claude", Action.LOGIN)
    idle(qtbot, manager)
    assert calls == []
    assert manager.sessions["claude"].message == "path_hint"
    assert manager.sessions["claude"].connection.action == Action.INSTALL


def test_error_exposes_copy_and_retry(rig, qtbot, monkeypatch):
    manager, *_ = rig
    idle(qtbot, manager)
    def fail(*args):
        raise LaunchError("terminal_missing")
    monkeypatch.setattr(recovery, "launch", fail)
    manager.activate("claude", Action.LOGIN)
    idle(qtbot, manager)
    assert manager.sessions["claude"].message == "terminal_missing"
    assert [label for label, fn in manager.actions("claude")] == ["Copy command", "Log in"]


def test_cancel_and_timeout_do_not_close_terminal(rig, qtbot):
    manager, state, calls, refreshed = rig
    idle(qtbot, manager)
    manager.activate("claude", Action.LOGIN)
    idle(qtbot, manager)
    manager.activate("claude", Action.CANCEL)
    assert not manager.sessions["claude"].waiting
    manager.activate("claude", Action.LOGIN)
    idle(qtbot, manager)
    manager.sessions["claude"].deadline = 0
    manager._tick()
    assert manager.sessions["claude"].message == "timeout"
    assert refreshed == []


def test_recheck_fetches_and_copy_uses_command_only(rig, qtbot, qapp):
    manager, state, calls, refreshed = rig
    idle(qtbot, manager)
    manager.activate("claude", Action.RECHECK)
    idle(qtbot, manager)
    assert refreshed == [True]
    manager.activate("claude", Action.COPY)
    assert qapp.clipboard().text() == "claude auth login"


def test_slow_probe_does_not_block_ui(qapp, qtbot, monkeypatch):
    from threading import Event

    from PySide6.QtCore import QTimer

    release = Event()
    def observe(key, config):
        release.wait(3)
        return Observation(Connection(key, None, "file", AuthState.MISSING))
    monkeypatch.setattr(recovery, "observe", observe)
    manager = recovery.LoginRecovery(Config({}), lambda: None)
    manager.start()
    painted = []
    QTimer.singleShot(0, lambda: painted.append(True))
    try:
        qtbot.waitUntil(lambda: bool(painted), timeout=1000)
        assert manager._jobs
    finally:
        release.set()
        manager.close()
        manager._pool.shutdown(wait=True)


def test_login_clicked_during_discovery_is_not_lost(rig, qtbot):
    manager, state, calls, refreshed = rig
    # The initial observation is still in the job map until the Qt timer runs.
    manager.activate("claude", Action.LOGIN)
    manager.activate("claude", Action.LOGIN)
    qtbot.waitUntil(lambda: manager.sessions["claude"].waiting, timeout=3000)
    assert len(calls) == 1


def test_unchanged_probe_does_not_rebuild_panel(rig, qtbot):
    manager, state, calls, refreshed = rig
    idle(qtbot, manager)
    changes = []
    manager.changed.connect(lambda: changes.append(True))
    manager._submit("claude", "probe")
    idle(qtbot, manager)
    assert changes == []
