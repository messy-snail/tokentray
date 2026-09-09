from __future__ import annotations

import json
import time

import httpx
import pytest
import respx

from tokentray.core.config import Config
from tokentray.core.models import Status
from tokentray.providers import build_providers
from tokentray.providers.base import SchemaError
from tokentray.providers.claude import USAGE_URL as CLAUDE_URL
from tokentray.providers.claude import ClaudeProvider
from tokentray.providers.codex import TOKEN_URL, USAGE_URL as CODEX_URL
from tokentray.providers.codex import CodexProvider

CLAUDE_BODY = {
    "five_hour": {"utilization": 48.0, "resets_at": "2026-09-07T16:00:00Z"},
    "seven_day": {"utilization": 19.0, "resets_at": "2026-09-14T00:00:00Z"},
    "seven_day_opus": {"utilization": 5.0, "resets_at": "2026-09-14T00:00:00Z"},
    "seven_day_sonnet": {"utilization": 0.0, "resets_at": "2026-09-14T00:00:00Z"},
    "spend": {
        "enabled": True,
        "used": {"amount_minor": 1234},
        "limit": {"amount_minor": 5000, "exponent": 2, "currency": "USD"},
    },
}

CODEX_BODY = {
    "plan_type": "plus",
    "rate_limit": {
        "primary_window": {
            "used_percent": 32.0,
            "reset_at": 1_788_000_000,
            "limit_window_seconds": 604800,
        },
        "secondary_window": {
            "used_percent": 10.0,
            "reset_at": 1_788_000_000,
            "limit_window_seconds": 18000,
        },
    },
    "credits": {"has_credits": True, "balance": 4.5},
}


@pytest.fixture
def claude(config, cache, claude_credentials):
    provider = ClaudeProvider(config, cache)
    yield provider
    provider.close()


@pytest.fixture
def codex(config, cache, codex_credentials):
    provider = CodexProvider(config, cache)
    yield provider
    provider.close()


class TestClaudeParsing:
    def test_full_response_yields_every_reported_window(self, claude):
        snapshot = claude.parse({**CLAUDE_BODY, "_subscription": "max"})
        keys = [w.key for w in snapshot.windows]
        # sonnet is at 0% so it stays hidden; opus is in use so it shows.
        assert keys == ["claude.5h", "claude.7d", "claude.7d_opus"]
        assert snapshot.plan == "max"

    def test_missing_seven_day_is_not_fatal(self, claude):
        body = {"five_hour": CLAUDE_BODY["five_hour"]}
        snapshot = claude.parse(body)
        assert [w.key for w in snapshot.windows] == ["claude.5h"]

    def test_missing_five_hour_is_a_schema_change(self, claude):
        with pytest.raises(SchemaError):
            claude.parse({"seven_day": CLAUDE_BODY["seven_day"]})

    def test_extra_usage_converts_minor_units(self, claude):
        extra = claude.parse(CLAUDE_BODY).extra
        assert extra is not None
        assert (extra.enabled, extra.used, extra.limit, extra.currency) == (True, 12.34, 50.0, "USD")

    def test_extra_usage_absent_without_a_limit(self, claude):
        assert claude.parse({**CLAUDE_BODY, "spend": {"enabled": False}}).extra is None


class TestClaudeCredentials:
    def test_reads_the_cli_credential_file(self, claude):
        creds = claude.credentials()
        assert creds is not None and creds.access_token == "sk-test-token"
        assert creds.subscription == "max"

    def test_empty_token_counts_as_not_configured(self, claude, claude_credentials):
        # Claude Code writes plan metadata with a blank token when the session is
        # authenticated elsewhere; that must not look like a usable login.
        claude_credentials.write_text(
            json.dumps({"claudeAiOauth": {"accessToken": "", "subscriptionType": "max"}}),
            encoding="utf-8",
        )
        assert claude.credentials() is None
        assert claude.fetch().status is Status.NOT_CONFIGURED

    def test_expiry_in_milliseconds_is_understood(self, claude, claude_credentials):
        claude_credentials.write_text(
            json.dumps(
                {"claudeAiOauth": {"accessToken": "tok", "expiresAt": int(time.time() * 1000) - 1000}}
            ),
            encoding="utf-8",
        )
        assert claude.fetch().status is Status.EXPIRED

    def test_expired_token_is_never_refreshed(self, claude, claude_credentials):
        # Claude Code owns that token; a second writer is how people get logged out.
        claude_credentials.write_text(
            json.dumps({"claudeAiOauth": {"accessToken": "tok", "expiresAt": 1000}}),
            encoding="utf-8",
        )
        with respx.mock:
            route = respx.get(CLAUDE_URL).mock(return_value=httpx.Response(200, json=CLAUDE_BODY))
            assert claude.fetch().status is Status.EXPIRED
            assert not route.called


class TestClaudeHttpStatuses:
    @pytest.mark.parametrize(
        "code,expected",
        [(401, Status.UNAUTHORIZED), (429, Status.RATE_LIMITED), (500, Status.ERROR)],
    )
    def test_status_mapping_without_cache(self, claude, code, expected):
        with respx.mock:
            respx.get(CLAUDE_URL).mock(return_value=httpx.Response(code))
            assert claude.fetch().status is expected

    def test_success_populates_cache_and_reports_live(self, claude):
        with respx.mock:
            respx.get(CLAUDE_URL).mock(return_value=httpx.Response(200, json=CLAUDE_BODY))
            snapshot = claude.fetch()
        assert snapshot.status is Status.OK
        assert snapshot.detail == "live"
        assert claude.cache.load("claude") is not None

    def test_two_hundred_with_unknown_shape_is_schema_changed(self, claude):
        with respx.mock:
            respx.get(CLAUDE_URL).mock(return_value=httpx.Response(200, json={"whatever": 1}))
            assert claude.fetch().status is Status.SCHEMA_CHANGED


class TestCacheAndBackoff:
    def test_second_call_inside_ttl_does_not_hit_the_network(self, claude):
        with respx.mock:
            route = respx.get(CLAUDE_URL).mock(return_value=httpx.Response(200, json=CLAUDE_BODY))
            claude.fetch()
            second = claude.fetch()
            assert route.call_count == 1
        assert second.status is Status.CACHED

    def test_force_bypasses_the_cache(self, claude):
        with respx.mock:
            route = respx.get(CLAUDE_URL).mock(return_value=httpx.Response(200, json=CLAUDE_BODY))
            claude.fetch()
            claude.fetch(force=True)
            assert route.call_count == 2

    def test_failure_falls_back_to_stale_data(self, claude):
        with respx.mock:
            respx.get(CLAUDE_URL).mock(return_value=httpx.Response(200, json=CLAUDE_BODY))
            claude.fetch(now=1000.0)
        with respx.mock:
            respx.get(CLAUDE_URL).mock(return_value=httpx.Response(429))
            stale = claude.fetch(force=True, now=1000.0 + 500)
        assert stale.status is Status.STALE
        assert stale.windows  # the old numbers are still shown

    def test_backoff_suppresses_requests_until_it_expires(self, claude):
        with respx.mock:
            respx.get(CLAUDE_URL).mock(return_value=httpx.Response(200, json=CLAUDE_BODY))
            claude.fetch(now=1000.0)
        with respx.mock:
            route = respx.get(CLAUDE_URL).mock(return_value=httpx.Response(500))
            claude.fetch(force=True, now=1500.0)   # fails, arms backoff
            claude.fetch(now=1520.0)               # inside backoff -> no request
            assert route.call_count == 1
        with respx.mock:
            route = respx.get(CLAUDE_URL).mock(return_value=httpx.Response(200, json=CLAUDE_BODY))
            claude.fetch(now=1500.0 + 200)         # backoff expired -> request again
            assert route.call_count == 1

    def test_expired_credentials_do_not_mask_themselves_as_stale(self, claude):
        # An actionable status must survive even when cached data exists,
        # otherwise the user never learns they have to log in again.
        with respx.mock:
            respx.get(CLAUDE_URL).mock(return_value=httpx.Response(200, json=CLAUDE_BODY))
            claude.fetch(now=1000.0)
        with respx.mock:
            respx.get(CLAUDE_URL).mock(return_value=httpx.Response(401))
            snapshot = claude.fetch(force=True, now=1100.0)
        assert snapshot.status is Status.UNAUTHORIZED


class TestCodexParsing:
    def test_windows_and_credits(self, codex):
        snapshot = codex.parse(CODEX_BODY)
        assert [w.key for w in snapshot.windows] == ["codex.primary", "codex.secondary"]
        assert snapshot.windows[0].label_args == {"window": "7d"}
        assert snapshot.windows[1].label_args == {"window": "5h"}
        assert snapshot.plan == "plus"
        assert snapshot.credits is not None and snapshot.credits.balance == 4.5

    def test_weekly_only_plan_reports_one_window(self, codex):
        body = {"rate_limit": {"primary_window": CODEX_BODY["rate_limit"]["primary_window"]}}
        snapshot = codex.parse(body)
        assert len(snapshot.windows) == 1
        assert snapshot.windows[0].label_args == {"window": "7d"}

    def test_missing_rate_limit_is_a_schema_change(self, codex):
        with pytest.raises(SchemaError):
            codex.parse({"plan_type": "plus"})

    def test_unlimited_credits_take_precedence(self, codex):
        body = {**CODEX_BODY, "credits": {"has_credits": True, "balance": 3, "unlimited": True}}
        credits = codex.parse(body).credits
        assert credits is not None and credits.unlimited is True

    def test_disabled_credits_are_omitted(self, codex):
        body = {**CODEX_BODY, "credits": {"has_credits": False, "balance": 0}}
        assert codex.parse(body).credits is None


class TestCodexCredentials:
    def test_api_key_mode_is_not_configured(self, codex, codex_credentials):
        # An API key cannot call the session-scoped usage endpoint at all.
        codex_credentials.write_text(json.dumps({"OPENAI_API_KEY": "sk-x"}), encoding="utf-8")
        assert codex.credentials() is None
        assert codex.fetch().status is Status.NOT_CONFIGURED

    def test_account_header_is_sent_when_known(self, codex):
        with respx.mock:
            route = respx.get(CODEX_URL).mock(return_value=httpx.Response(200, json=CODEX_BODY))
            codex.fetch()
        assert route.calls[0].request.headers["ChatGPT-Account-Id"] == "acct_123"
        assert route.calls[0].request.headers["originator"] == "codex_cli_rs"


class TestCodexRefresh:
    def test_refresh_is_off_by_default(self, codex):
        with respx.mock:
            respx.get(CODEX_URL).mock(return_value=httpx.Response(401))
            token = respx.post(TOKEN_URL)
            snapshot = codex.fetch()
        assert snapshot.status is Status.EXPIRED
        assert not token.called

    def test_opt_in_refresh_retries_and_persists(self, cache, codex_credentials):
        config = Config({"codex": {"refresh": True}})
        provider = CodexProvider(config, cache)
        with respx.mock:
            respx.post(TOKEN_URL).mock(
                return_value=httpx.Response(200, json={"access_token": "new-access"})
            )
            usage = respx.get(CODEX_URL)
            usage.side_effect = [
                httpx.Response(401),
                httpx.Response(200, json=CODEX_BODY),
            ]
            snapshot = provider.fetch()
        provider.close()
        assert snapshot.status is Status.OK
        written = json.loads(codex_credentials.read_text(encoding="utf-8"))
        assert written["tokens"]["access_token"] == "new-access"
        assert "last_refresh" in written

    def test_concurrent_cli_write_is_not_clobbered(self, cache, codex_credentials):
        config = Config({"codex": {"refresh": True}})
        provider = CodexProvider(config, cache)
        creds = provider.credentials()
        assert creds is not None

        # Simulate the Codex CLI rewriting auth.json while our refresh is in flight.
        codex_credentials.write_text(
            json.dumps({"tokens": {"access_token": "cli-wrote-this"}}), encoding="utf-8"
        )
        import os

        os.utime(codex_credentials, (creds.mtime + 10, creds.mtime + 10))

        with respx.mock:
            respx.post(TOKEN_URL).mock(
                return_value=httpx.Response(200, json={"access_token": "ours"})
            )
            provider._maybe_refresh(creds)
        provider.close()

        assert json.loads(codex_credentials.read_text(encoding="utf-8"))["tokens"][
            "access_token"
        ] == "cli-wrote-this"


class TestRegistry:
    def test_disabled_providers_are_not_built(self, cache):
        config = Config({"codex": {"enabled": False}})
        ids = [p.id for p in build_providers(config, cache)]
        assert ids == ["claude"]


def test_registry_order_matches_the_documented_ring_order():
    # The tray icon draws views in the order app.py hands them over - outermost
    # ring first - and nothing sorts along the way. If a provider is added or
    # reordered here, PROVIDER_ORDER has to move with it.
    from tokentray.core.view import PROVIDER_ORDER
    from tokentray.providers import PROVIDER_CLASSES

    assert tuple(cls.id for cls in PROVIDER_CLASSES) == PROVIDER_ORDER
