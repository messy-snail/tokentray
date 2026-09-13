"""A refused keychain read must not be retried until the user asks.

While macOS refuses the Claude Code keychain item, each ``security`` call can
bring the authorization prompt back. The poll timer and the two-second login
probe both called it without limit, and the refusal read as "not logged in",
which sent the user into exactly that probe loop.
"""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from tokentray import connections as c
from tokentray.core import i18n
from tokentray.core.config import Config
from tokentray.core.models import Status
from tokentray.core.secrets import CLAUDE_ACCESS_TOKEN, SecretStore
from tokentray.core.view import status_message
from tokentray.providers import claude
from tokentray.providers.base import CredentialsUnreadable
from tokentray.providers.claude import ClaudeProvider

GRANTED = json.dumps({"claudeAiOauth": {"accessToken": "tok", "expiresAt": 4_102_444_800_000}})


@pytest.fixture
def store(tmp_path, monkeypatch):
    result = SecretStore(tmp_path / "secrets.toml")
    monkeypatch.setattr(result, "_keyring", lambda: None)
    return result


@pytest.fixture
def keychain(claude_credentials, monkeypatch):
    """macOS, no credential file, and a ``security`` whose answer the test sets."""
    claude_credentials.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(claude.sys, "platform", "darwin")
    answer = SimpleNamespace(code=51, stdout="", calls=0)

    def run(argv, **kwargs):
        answer.calls += 1
        if answer.code == "timeout":
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))
        return subprocess.CompletedProcess(argv, answer.code, stdout=answer.stdout, stderr="")

    monkeypatch.setattr(claude.subprocess, "run", run)
    return answer


@pytest.fixture
def reader(keychain, config, cache, store):
    provider = ClaudeProvider(config, cache, secrets=store)
    yield provider
    provider.close()


class TestReadingTheKeychain:
    def test_a_missing_item_only_means_logged_out(self, keychain, reader):
        keychain.code = 44
        assert reader.credentials() is None
        assert reader.fetch().status is Status.NOT_CONFIGURED

    @pytest.mark.parametrize("code", [51, 128, "timeout"])
    def test_any_other_failure_is_unreadable(self, keychain, reader, code):
        keychain.code = code
        with pytest.raises(CredentialsUnreadable):
            reader.credentials()

    def test_a_pasted_token_still_works_while_the_keychain_refuses(self, reader, store):
        store.set(CLAUDE_ACCESS_TOKEN, "manual")
        assert reader.credentials().source == "manual"


class TestTheRefusalIsRemembered:
    def test_polls_do_not_ask_again(self, keychain, reader):
        for _ in range(3):
            assert reader.fetch().status is Status.UNREADABLE
        assert keychain.calls == 1

    def test_a_forced_refresh_asks_again(self, keychain, reader):
        reader.fetch()
        reader.fetch(force=True)
        assert keychain.calls == 2

    def test_access_granted_later_resumes_automatic_reads(self, keychain, reader):
        reader.fetch()
        keychain.code, keychain.stdout = 0, GRANTED
        assert reader.credentials(interactive=True).source == "keychain"
        assert reader.credentials().source == "keychain"
        assert keychain.calls == 3

    def test_it_is_not_shown_as_logged_out(self, reader):
        from tokentray.login_recovery import AUTH_REQUIRED

        snapshot = reader.fetch()
        assert snapshot.status is Status.UNREADABLE
        assert snapshot.status not in AUTH_REQUIRED
        assert snapshot.status.is_actionable
        assert status_message(snapshot) == i18n.t("status.unreadable_claude")


class TestTheConnectionProbe:
    def test_it_names_the_keychain(self, keychain, store):
        observation = c.observe("claude", Config({}), store)
        assert observation.connection.auth == c.AuthState.UNREADABLE
        assert observation.connection.source == "keychain"
        assert c.keychain_refused(observation)

    def test_repeated_probes_ask_once(self, keychain, store):
        for _ in range(5):
            c.observe("claude", Config({}), store)
        assert keychain.calls == 1

    def test_an_explicit_check_asks_again(self, keychain, store):
        c.observe("claude", Config({}), store)
        c.observe("claude", Config({}), store, interactive=True)
        assert keychain.calls == 2
