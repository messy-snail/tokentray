from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tokentray import connections as c
from tokentray import login_terminal as terminal
from tokentray.core.config import Config
from tokentray.core.secrets import CLAUDE_ACCESS_TOKEN, SecretStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    result = SecretStore(tmp_path / "secrets.toml")
    monkeypatch.setattr(result, "_keyring", lambda: None)
    return result


def test_credentials_do_not_require_cli(claude_credentials, store, monkeypatch):
    monkeypatch.setattr(c, "find_cli", lambda key: None)
    result = c.inspect("claude", Config({}), store)
    assert result.auth == c.AuthState.FOUND
    assert result.action == c.Action.INSTALL
    assert result.source == "file"
    assert "sk-test-token" not in repr(result)


def test_expiry_is_not_detection_success(claude_credentials, store):
    data = json.loads(claude_credentials.read_text())
    data["claudeAiOauth"]["expiresAt"] = 1000
    claude_credentials.write_text(json.dumps(data))
    assert c.inspect("claude", Config({}), store).auth == c.AuthState.EXPIRED


@pytest.mark.parametrize("data, state", [
    ('{"OPENAI_API_KEY":"test-key"}', c.AuthState.UNSUPPORTED),
    ('{invalid', c.AuthState.UNREADABLE),
    ('[]', c.AuthState.UNREADABLE),
    ('{}', c.AuthState.MISSING),
])
def test_file_diagnostics(codex_credentials, store, data, state):
    codex_credentials.write_text(data)
    assert c.inspect("codex", Config({}), store).auth == state


def test_manual_fallback_and_fingerprint(claude_credentials, store):
    claude_credentials.write_text("{}")
    store.set(CLAUDE_ACCESS_TOKEN, "manual-a")
    first = c.observe("claude", Config({}), store)
    store.set(CLAUDE_ACCESS_TOKEN, "manual-b")
    second = c.observe("claude", Config({}), store)
    assert first.connection.source == "manual"
    assert first.connection.auth == c.AuthState.FOUND
    assert first.fingerprint != second.fingerprint
    assert "manual-a" not in repr(first)


def test_keychain_uses_provider_precedence(claude_credentials, store, monkeypatch):
    from tokentray.providers import claude

    monkeypatch.setattr(claude.sys, "platform", "darwin")
    monkeypatch.setattr(claude, "_from_keychain", lambda: claude.ClaudeCreds("keychain", None, source="keychain"))
    assert c.inspect("claude", Config({}), store).source == "file"
    claude_credentials.write_text("{}")
    assert c.inspect("claude", Config({}), store).source == "keychain"


def test_custom_auth_path_and_missing_credentials(tmp_path, store, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "custom"))
    assert c.inspect("codex", Config({}), store).auth == c.AuthState.MISSING
    path = tmp_path / "custom/auth.json"
    path.parent.mkdir()
    path.write_text('{"tokens":{"access_token":"test-custom"}}')
    assert c.inspect("codex", Config({}), store).auth == c.AuthState.FOUND


def test_codex_expiry_is_only_a_local_hint(codex_credentials, store):
    payload = base64.urlsafe_b64encode(b'{"exp":1}').decode().rstrip("=")
    codex_credentials.write_text(json.dumps({"tokens": {"access_token": f"head.{payload}.sig"}}))
    assert c.inspect("codex", Config({}), store).auth == c.AuthState.EXPIRED
    codex_credentials.write_text(json.dumps({"tokens": {"access_token": "opaque-token"}}))
    assert c.inspect("codex", Config({}), store).auth == c.AuthState.FOUND


def test_expiry_metadata_change_is_observed(claude_credentials, store):
    first = c.observe("claude", Config({}), store)
    data = json.loads(claude_credentials.read_text())
    data["claudeAiOauth"]["expiresAt"] += 1000
    claude_credentials.write_text(json.dumps(data))
    assert c.observe("claude", Config({}), store).fingerprint != first.fingerprint


def test_path_search_precedes_standard_installation(monkeypatch, tmp_path):
    path = tmp_path / "custom cli.exe"
    monkeypatch.setattr(c.shutil, "which", lambda key: str(path))
    assert c.find_cli("claude") == path


def test_windows_native_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(c.sys, "platform", "win32")
    monkeypatch.setattr(c.shutil, "which", lambda key: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    path = tmp_path / ".local/bin/claude.exe"
    path.parent.mkdir(parents=True)
    path.touch()
    assert c.find_cli("claude") == path


@pytest.mark.parametrize("provider, tail", [("claude", "'auth' 'login'"), ("codex", "'login'")])
def test_windows_literal_arguments(monkeypatch, provider, tail):
    monkeypatch.setattr(terminal.sys, "platform", "win32")
    monkeypatch.setattr(terminal.shutil, "which", lambda key: "pwsh.exe")
    path = Path("C:/사용자/O'Brien $x & `(test)/cli.exe")
    argv = terminal.terminal_command(provider, path)
    script = base64.b64decode(argv[-1]).decode("utf-16-le")
    assert argv[0] == "pwsh.exe"
    assert "-NoProfile" in argv and "-NoExit" in argv
    assert script == "& '" + str(path).replace("'", "''") + "' " + tail


def test_windows_powershell_fallback(monkeypatch):
    monkeypatch.setattr(terminal.sys, "platform", "win32")
    monkeypatch.setattr(terminal.shutil, "which", lambda key: None if key == "pwsh" else "powershell.exe")
    assert terminal.terminal_command("codex", Path("codex.exe"))[0] == "powershell.exe"


def test_macos_carries_auth_environment(monkeypatch):
    import shlex

    monkeypatch.setattr(terminal.sys, "platform", "darwin")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/tmp/한글 ' $x")
    monkeypatch.setenv("CODEX_HOME", "/tmp/codex space")
    path = Path("/tmp/cli ' name")
    argv = terminal.terminal_command("claude", path)
    script = next(item for item in argv if item.startswith("do script "))
    command = json.loads(script.removeprefix("do script "))
    assert shlex.split(command) == ["/usr/bin/env", "CLAUDE_CONFIG_DIR=/tmp/한글 ' $x",
                                   "CODEX_HOME=/tmp/codex space", str(path), "auth", "login"]


@pytest.mark.parametrize("name", ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"])
def test_linux_terminal_adapters(monkeypatch, name):
    monkeypatch.setattr(terminal.sys, "platform", "linux")
    monkeypatch.setattr(terminal.shutil, "which", lambda key: "/usr/bin/" + key if key == name else None)
    argv = terminal.terminal_command("codex", Path("/tmp/a b/codex"))
    assert argv[0] == "/usr/bin/" + name
    assert "login" in " ".join(argv)
    if name == "gnome-terminal":
        assert argv[1:3] == ["--wait", "--"]


def test_no_terminal_and_popen_failure(monkeypatch):
    monkeypatch.setattr(terminal.sys, "platform", "linux")
    monkeypatch.setattr(terminal.shutil, "which", lambda key: None)
    with pytest.raises(terminal.LaunchError, match="terminal_missing"):
        terminal.launch("claude", Path("/cli"))
    monkeypatch.setattr(terminal.shutil, "which", lambda key: "/usr/bin/xterm")
    def fail(*args, **kwargs):
        raise OSError("test")
    monkeypatch.setattr(terminal.subprocess, "Popen", fail)
    with pytest.raises(terminal.LaunchError, match="terminal_failed"):
        terminal.launch("claude", Path("/cli"))


def test_nonzero_launcher_exit(monkeypatch):
    monkeypatch.setattr(terminal.sys, "platform", "linux")
    monkeypatch.setattr(terminal.shutil, "which", lambda key: "/usr/bin/xterm")
    monkeypatch.setattr(terminal.subprocess, "Popen", lambda *a, **kw: SimpleNamespace(wait=lambda **k: 1))
    with pytest.raises(terminal.LaunchError, match="terminal_failed"):
        terminal.launch("codex", Path("/cli"))
