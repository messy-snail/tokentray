from __future__ import annotations

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from tokentray import cli, launcher


@pytest.fixture
def launch_environment(monkeypatch, isolated_config):
    replies = iter([None, {"ok": True}])
    monkeypatch.setattr(launcher.ipc, "send_command", lambda *a, **kw: next(replies))
    monkeypatch.setattr(launcher, "gui_command", lambda: ["path with spaces/python", "-m", "tokentray.app"])
    calls = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **kw: calls.append((a, kw)))
    return calls


def test_start_detaches_stdio_and_preserves_arguments(launch_environment):
    assert launcher.start(autostart=True) == 0
    args, options = launch_environment[0]
    assert args[0] == ["path with spaces/python", "-m", "tokentray.app", "--autostart"]
    assert options["stdin"] == launcher.subprocess.DEVNULL
    assert options["stderr"] == launcher.subprocess.STDOUT
    assert options["close_fds"]
    assert "shell" not in options
    if launcher.sys.platform == "win32":
        assert options["creationflags"] & launcher.subprocess.DETACHED_PROCESS
        assert options["creationflags"] & launcher.subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert options["start_new_session"]


def test_running_instance_is_shown_without_spawning(monkeypatch, launch_environment):
    commands = []
    monkeypatch.setattr(launcher.ipc, "send_command", lambda command, **kw: commands.append(command) or {"ok": True})
    assert launcher.start() == 0
    assert commands == [launcher.ipc.CMD_SHOW]
    assert not launch_environment


def test_spawn_failure_returns_nonzero(monkeypatch, launch_environment, capsys):
    def fail(*a, **kw):
        raise FileNotFoundError("private path")
    monkeypatch.setattr(launcher.subprocess, "Popen", fail)
    assert launcher.start() == 1
    assert "--foreground" in capsys.readouterr().out


def test_early_child_exit_is_not_reported_as_success(monkeypatch, launch_environment):
    monkeypatch.setattr(launcher.ipc, "send_command", lambda *a, **kw: None)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **kw: SimpleNamespace(poll=lambda: 1, returncode=1))
    assert launcher.start() == 1


def test_slow_start_reports_pending_without_killing_child(monkeypatch, launch_environment, capsys):
    monkeypatch.setattr(launcher.ipc, "send_command", lambda *a, **kw: None)
    times = iter([0, 11])
    monkeypatch.setattr(launcher.time, "monotonic", lambda: next(times))
    assert launcher.start() == 0
    assert "not responding yet" in capsys.readouterr().out


@pytest.mark.parametrize("args", [[], ["run"]])
def test_default_cli_launch_is_background(monkeypatch, args):
    calls = []
    monkeypatch.setattr(launcher, "start", lambda **kw: calls.append(kw) or 0)
    assert CliRunner().invoke(cli.app, args).exit_code == 0
    assert calls == [{"autostart": False}]


def test_foreground_calls_gui_directly(monkeypatch):
    from tokentray import app

    calls = []
    monkeypatch.setattr(app, "main", lambda **kw: calls.append(kw) or 0)
    assert CliRunner().invoke(cli.app, ["run", "--foreground"]).exit_code == 0
    assert calls == [{"autostart": False}]


def test_python_command_uses_current_install_not_path(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher.sys, "frozen", False, raising=False)
    monkeypatch.setattr(launcher.sys, "executable", str(tmp_path / "python.exe"))
    expected = tmp_path / "python.exe"
    if launcher.sys.platform == "win32":
        expected = tmp_path / "pythonw.exe"
        expected.touch()
    assert launcher.gui_command() == [str(expected), "-m", "tokentray.app"]


def test_missing_frozen_gui_does_not_recursively_launch_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher.sys, "frozen", True, raising=False)
    monkeypatch.setattr(launcher.sys, "executable", str(tmp_path / "tokentray.exe"))
    with pytest.raises(FileNotFoundError):
        launcher.gui_command()


def test_setup_starts_in_background(monkeypatch, isolated_config):
    from tokentray import setup_wizard as wizard
    from tokentray.core.config import Config

    monkeypatch.setattr(wizard, "_choose_language", lambda *a: None)
    monkeypatch.setattr(wizard, "_choose_autostart", lambda: None)
    monkeypatch.setattr(wizard, "PROVIDERS", [])
    monkeypatch.setattr(wizard.typer, "confirm", lambda *a, **kw: True)
    calls = []
    monkeypatch.setattr(launcher, "start", lambda: calls.append(True) or 0)
    assert wizard.run(Config({}), store=object()) == 0
    assert calls == [True]
