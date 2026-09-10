"""Tests for re-arming what tokentray only ever says once.

Three separate memories conspired to make a working app look broken: the welcome
flag, the fired thresholds, and a state file the running app rewrites on every
poll. These cover clearing each of them, and clearing them somewhere that lasts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from tokentray import ipc
from tokentray.cli import app as cli_app
from tokentray.core import paths, state
from tokentray.core.alerts import AlertState, evaluate
from tokentray.core.models import Snapshot, Status, UsageWindow
from tokentray.core.view import build_view

runner = CliRunner()

NOW_DT = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
NOW = 1_757_246_400.0


def output(result) -> str:
    try:
        return (result.stdout or "") + (result.stderr or "")
    except ValueError:  # older Click merges the streams
        return result.output or ""


def fired_state() -> AlertState:
    """What the reporting user's machine actually held: 50% already announced."""
    return AlertState(
        threshold={"claude.5h": 50},
        remind={},
        last_used={"claude.5h": 73.0},
        notified_status={},
        paused_until=0.0,
        seeded=True,
    )


def view_at(used: float):
    return build_view(
        Snapshot(
            provider="claude",
            status=Status.OK,
            windows=[
                UsageWindow(
                    key="claude.5h",
                    used_pct=used,
                    resets_at=NOW_DT + timedelta(seconds=7200),
                    window_secs=18_000,
                )
            ],
        ),
        NOW_DT,
    )


class TestClearing:
    def test_clear_welcome_pops_the_key(self):
        data = {"welcomed": True, "alerts": {}}
        state.clear_welcome(data)
        # Absent, not False: the gate in Controller.start tests truthiness, and a
        # stored False would read as "already shown" to a presence check.
        assert "welcomed" not in data

    def test_clear_welcome_on_a_fresh_state_is_harmless(self):
        data: dict = {}
        state.clear_welcome(data)
        assert data == {}

    def test_clear_alerts_keeps_the_pause_and_the_seed(self):
        data = {"alerts": dict(fired_state().to_dict(), paused_until=NOW + 3600)}
        state.clear_alerts(data)
        alerts = data["alerts"]
        assert alerts["paused_until"] == NOW + 3600
        assert alerts["seeded"] is True
        assert alerts["threshold"] == {}
        assert alerts["remind"] == {}
        assert alerts["last_used"] == {}
        assert alerts["notified_status"] == {}

    def test_a_cleared_state_can_fire_again(self):
        """The whole point: after a reset the next poll actually says something."""
        args = dict(thresholds=[50, 25, 10], remind_before=[], now=NOW, clock=NOW_DT)
        already = fired_state()
        assert evaluate([view_at(73.0)], state=already, **args) == []

        rearmed = already.cleared()
        events = evaluate([view_at(73.0)], state=rearmed, **args)
        assert [(e.kind, e.key) for e in events] == [("threshold", "claude.5h")]
        # 27% remaining crosses the lowest armed threshold, not every one above it.
        assert rearmed.threshold == {"claude.5h": 50}


class TestTheRunningApp:
    def test_the_reset_survives_the_next_save(self, qapp, isolated_config):
        """A file write underneath the app would be undone within one poll."""
        from tokentray import app as app_mod
        from tokentray.core.config import Config

        controller = app_mod.Controller(qapp, Config({"poll_interval": 120}))
        controller._state["welcomed"] = True
        controller._save_state()

        controller._handle_command(ipc.CMD_RESET_WELCOME)
        assert "welcomed" not in controller._state
        controller._save_state()
        assert "welcomed" not in state.load()

    def test_resetting_alerts_keeps_the_pause(self, qapp, isolated_config):
        from tokentray import app as app_mod
        from tokentray.core.config import Config

        controller = app_mod.Controller(qapp, Config({"poll_interval": 120}))
        controller.alerts = fired_state()
        controller.alerts.paused_until = NOW + 3600

        controller._handle_command(ipc.CMD_RESET_ALERTS)
        assert controller.alerts.threshold == {}
        assert controller.alerts.paused_until == NOW + 3600


class TestTheCommand:
    @pytest.fixture
    def sent(self, monkeypatch):
        """Record the IPC conversation and answer as a live, unpaused app."""
        recorded: list[str] = []

        def send(command, timeout=2.0):
            recorded.append(command)
            return {"ok": True, "paused": False}

        monkeypatch.setattr(ipc, "send_command", send)
        return recorded

    @pytest.fixture
    def offline(self, monkeypatch):
        monkeypatch.setattr(ipc, "send_command", lambda command, timeout=2.0: None)

    def test_a_live_instance_is_used_instead_of_the_file(self, isolated_config, sent):
        state.save({"welcomed": True})
        before = paths.state_file().read_text(encoding="utf-8")
        result = runner.invoke(cli_app, ["state", "reset", "--welcome"])
        assert result.exit_code == 0
        assert sent == [ipc.CMD_STATUS, ipc.CMD_RESET_WELCOME]
        assert paths.state_file().read_text(encoding="utf-8") == before
        assert "the running app" in output(result)

    def test_without_an_instance_the_file_is_written(self, isolated_config, offline):
        state.save({"welcomed": True, "alerts": fired_state().to_dict()})
        result = runner.invoke(cli_app, ["state", "reset", "--welcome"])
        assert result.exit_code == 0
        data = state.load()
        assert "welcomed" not in data
        # Only what was asked for: the alert memory is a separate flag.
        assert data["alerts"]["threshold"] == {"claude.5h": 50}
        assert str(paths.state_file()) in output(result)

    def test_all_resets_both(self, isolated_config, sent):
        result = runner.invoke(cli_app, ["state", "reset", "--all"])
        assert result.exit_code == 0
        assert sent == [ipc.CMD_STATUS, ipc.CMD_RESET_WELCOME, ipc.CMD_RESET_ALERTS]
        assert "welcome and alerts" in output(result)

    def test_alerts_alone_leaves_the_welcome_alone(self, isolated_config, offline):
        state.save({"welcomed": True, "alerts": fired_state().to_dict()})
        assert runner.invoke(cli_app, ["state", "reset", "--alerts"]).exit_code == 0
        data = state.load()
        assert data["welcomed"] is True
        assert data["alerts"]["threshold"] == {}

    def test_no_flag_is_an_error(self, isolated_config, offline):
        state.save({"welcomed": True})
        result = runner.invoke(cli_app, ["state", "reset"])
        assert result.exit_code == 1
        text = output(result)
        for flag in ("--welcome", "--alerts", "--all"):
            assert flag in text
        assert state.load() == {"welcomed": True}

    def test_a_paused_instance_is_called_out(self, isolated_config, monkeypatch):
        monkeypatch.setattr(
            ipc, "send_command", lambda command, timeout=2.0: {"ok": True, "paused": True}
        )
        out = output(runner.invoke(cli_app, ["state", "reset", "--alerts"]))
        assert "alerts are paused" in out

    def test_a_pause_is_not_mentioned_when_only_the_welcome_is_reset(self, isolated_config, monkeypatch):
        monkeypatch.setattr(
            ipc, "send_command", lambda command, timeout=2.0: {"ok": True, "paused": True}
        )
        out = output(runner.invoke(cli_app, ["state", "reset", "--welcome"]))
        assert "alerts are paused" not in out
