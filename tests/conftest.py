from __future__ import annotations

import json
import os
from pathlib import Path

# Qt must never try to reach a real display from the suite: CI runners have none,
# and a developer running tests should not get windows flashing on screen.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from tokentray.core import i18n
from tokentray.core.cache import Cache
from tokentray.core.config import Config


@pytest.fixture(autouse=True)
def isolate_environment(tmp_path, monkeypatch):
    """Keep every test off the developer's real credentials and config.

    Providers fall back to the user's home directory when these are unset, which
    would make results depend on whoever runs the suite.
    """
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    i18n.set_language("en")
    yield
    i18n.set_language("en")


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point every path helper at a scratch directory."""
    from tokentray.core import paths

    for name in ("config_dir", "cache_dir", "state_dir", "log_dir", "runtime_dir"):
        target = tmp_path / name
        target.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(paths, name, lambda t=target: t)
    return tmp_path


@pytest.fixture
def config() -> Config:
    return Config({"poll_interval": 120})


@pytest.fixture
def cache(tmp_path) -> Cache:
    return Cache(tmp_path / "cache")


@pytest.fixture
def claude_credentials(tmp_path) -> Path:
    path = tmp_path / "claude" / ".credentials.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "sk-test-token",
                    "subscriptionType": "max",
                    "expiresAt": 4_102_444_800_000,  # year 2100, in milliseconds
                }
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def codex_credentials(tmp_path) -> Path:
    path = tmp_path / "codex" / "auth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": "codex-access",
                    "refresh_token": "codex-refresh",
                    "account_id": "acct_123",
                }
            }
        ),
        encoding="utf-8",
    )
    return path
