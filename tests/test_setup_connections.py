from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from tokentray import setup_display as display, setup_wizard as wizard
from tokentray.connections import AuthState, Connection
from tokentray.core import i18n
from tokentray.core.config import Config
from tokentray.core.secrets import SecretStore


def connection(auth=AuthState.MISSING, executable=None):
    return Connection("claude", executable, "file", auth)


def test_recheck_reuses_detection_and_enables(monkeypatch, tmp_path):
    states = iter([connection(), connection(AuthState.FOUND)])
    monkeypatch.setattr(wizard, "inspect", lambda *a: next(states))
    monkeypatch.setattr(wizard.typer, "prompt", lambda *a, **kw: "r")
    config = Config({})
    assert wizard._configure_provider(wizard.PROVIDERS[0], config, SecretStore(tmp_path / "s.toml"))
    assert config.get("claude.enabled")


def test_install_guide_is_explicit_and_does_not_install(monkeypatch, tmp_path):
    monkeypatch.setattr(wizard, "inspect", lambda *a: connection())
    answers = iter(["i", "s"])
    monkeypatch.setattr(wizard.typer, "prompt", lambda *a, **kw: next(answers))
    opened = []
    monkeypatch.setattr(wizard.webbrowser, "open", opened.append)
    assert not wizard._configure_provider(wizard.PROVIDERS[0], Config({}), SecretStore(tmp_path / "s.toml"))
    assert opened == [wizard.INSTALL_URLS["claude"]]


@pytest.mark.parametrize("language", ["ko", "en"])
@pytest.mark.parametrize("width, terminal", [(40, True), (110, True), (110, False)])
def test_rich_plain_and_narrow_output(monkeypatch, language, width, terminal):
    i18n.set_language(language)
    stream = io.StringIO()
    console = Console(file=stream, width=width, force_terminal=terminal)
    monkeypatch.setattr(display, "console", lambda: console)
    display.show_connections([connection(AuthState.FOUND, Path("/cli"))], introduction=True)
    text = stream.getvalue()
    assert "Claude Code" in text
    assert i18n.t("connect.connected") not in text
    if not terminal:
        assert "\x1b[" not in text


def test_cp949_output(monkeypatch):
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp949")
    monkeypatch.setattr(display.sys, "stdout", stream)
    i18n.set_language("ko")
    display.show_connections([connection(AuthState.EXPIRED)], introduction=True)
    display.say(i18n.t("connect.waiting"))
    stream.flush()
    assert "TokenTray" in stream.buffer.getvalue().decode("cp949")


def test_readonly_doctor_uses_same_detector(monkeypatch, isolated_config):
    from tokentray import diagnostics, connections

    monkeypatch.setattr(connections, "inspect", lambda key, config: Connection(key, None, "manual", AuthState.FOUND))
    monkeypatch.setattr(diagnostics, "qt_facts", lambda: {"platform": "offscreen", "tray": False, "supports_messages": False})
    result = "\n".join(diagnostics.report(Config({})))
    assert "Found; connection unverified (manual)" in result
    assert "poll interval" in result


def test_setup_login_waits_for_change_then_checks_provider(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from tokentray.connections import Observation
    from tokentray.core.models import Status

    observations = iter([Observation(connection(AuthState.EXPIRED, Path("/cli")), "before"),
                         Observation(connection(AuthState.FOUND, Path("/cli")), "after")])
    monkeypatch.setattr(wizard, "observe", lambda *args: next(observations))
    launches, fetched = [], []
    monkeypatch.setattr(wizard, "launch", lambda *args: launches.append(args))
    monkeypatch.setattr(wizard.time, "sleep", lambda seconds: None)
    def fetch(**kwargs):
        fetched.append(kwargs)
        return SimpleNamespace(status=Status.OK)
    monkeypatch.setattr(wizard, "make_provider", lambda *args: SimpleNamespace(fetch=fetch, close=lambda: None))
    result = wizard._login("claude", Config({}), SecretStore(tmp_path / "s.toml"))
    assert result == Status.OK
    assert len(launches) == 1
    assert fetched == [{"force": True}]


def test_setup_timeout_does_not_fetch(monkeypatch, tmp_path, capsys):
    from tokentray.connections import Observation

    monkeypatch.setattr(wizard, "observe", lambda *args: Observation(connection(AuthState.FOUND, Path("/cli")), "same"))
    monkeypatch.setattr(wizard, "launch", lambda *args: None)
    clock = iter([0, 301])
    monkeypatch.setattr(wizard.time, "monotonic", lambda: next(clock))
    wizard._login("claude", Config({}), SecretStore(tmp_path / "s.toml"))
    assert "Stopped waiting" in capsys.readouterr().out


@pytest.mark.parametrize("data", ['[]', '{"tokens":"broken"}'])
def test_legacy_doctor_details_tolerate_damaged_files(data, tmp_path):
    from tokentray.diagnostics import credential_state

    path = tmp_path / "auth.json"
    path.write_text(data)
    assert credential_state(path, "codex") == "unreadable"
