from __future__ import annotations

import json
import time
from copy import deepcopy
from datetime import datetime, timezone

import httpx
import pytest
import respx

from tokentray.core.alerts import AlertState, evaluate
from tokentray.core.config import Config
from tokentray.core.models import Status
from tokentray.core.view import build_view, tooltip
from tokentray.providers import build_providers
from tokentray.providers.base import SchemaError
from tokentray.providers.claude import USAGE_URL as CLAUDE_URL
from tokentray.providers.claude import ClaudeProvider
from tokentray.providers.codex import TOKEN_URL, CodexProvider
from tokentray.providers.codex import USAGE_URL as CODEX_URL

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

# Shaped after a real response from a weekly-only plan: the account's own quota
# has no five-hour slot at all, and the only one in the payload belongs to a
# per-model bucket that has not been touched yet.
CODEX_SUBLIMIT_BODY = {
    "plan_type": "prolite",
    "rate_limit": {
        "primary_window": {
            "used_percent": 63.0,
            "reset_at": 1_789_444_489,
            "limit_window_seconds": 604800,
        },
        "secondary_window": None,
    },
    "code_review_rate_limit": None,
    "additional_rate_limits": [
        {
            "limit_name": "GPT-5.3-Codex-Spark",
            "metered_feature": "codex_bengalfox",
            "rate_limit": {
                "primary_window": {
                    "used_percent": 0,
                    "reset_at": 1_788_980_629,
                    "limit_window_seconds": 18000,
                },
                "secondary_window": {
                    "used_percent": 0,
                    "reset_at": 1_789_567_429,
                    "limit_window_seconds": 604800,
                },
            },
        }
    ],
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
    def test_cached_snapshot_keeps_original_fetch_time(self, claude):
        claude.cache.store("claude", CLAUDE_BODY, now=1000.0)
        snapshot = claude.fetch(now=1073.0)
        assert snapshot.status is Status.CACHED
        assert snapshot.fetched_at == 1000.0

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
        assert stale.fetched_at == 1000.0
        assert stale.windows  # the old numbers are still shown

    def test_backoff_suppresses_requests_until_it_expires(self, claude):
        with respx.mock:
            respx.get(CLAUDE_URL).mock(return_value=httpx.Response(200, json=CLAUDE_BODY))
            claude.fetch(now=1000.0)
        with respx.mock:
            route = respx.get(CLAUDE_URL).mock(return_value=httpx.Response(500))
            claude.fetch(force=True, now=1500.0)   # fails, arms backoff
            cached = claude.fetch(now=1520.0)       # inside backoff -> no request
            assert cached.fetched_at == 1000.0
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
        assert snapshot.windows[0].window_secs == 604800
        assert snapshot.windows[1].window_secs == 18000
        assert snapshot.plan == "plus"
        assert snapshot.credits is not None and snapshot.credits.balance == 4.5

    def test_weekly_only_plan_with_no_sub_limits_reports_one_window(self, codex):
        body = {"rate_limit": {"primary_window": CODEX_BODY["rate_limit"]["primary_window"]}}
        snapshot = codex.parse(body)
        assert len(snapshot.windows) == 1
        assert snapshot.windows[0].window_secs == 604800

    @pytest.mark.parametrize("used", [0, 40, 100])
    @pytest.mark.parametrize("identity", [
        {"metered_feature": "codex_bengalfox"},
        {"metered_feature": " CODEX_BENGALFOX ", "limit_name": "Other"},
        {"limit_name": "GPT-5.3-Codex-Spark"},
        {"metered_feature": "unknown", "limit_name": " GPT-5.3-Codex-sPaRk "},
        {"metered_feature": None, "limit_name": "Spark"},
    ])
    def test_spark_windows_are_excluded(self, codex, used, identity):
        body = deepcopy(CODEX_SUBLIMIT_BODY)
        rate = body["additional_rate_limits"][0]["rate_limit"]
        for window in rate.values():
            window["used_percent"] = used
        body["additional_rate_limits"] = [{**identity, "rate_limit": rate}]
        snapshot = codex.parse(body)
        assert [w.key for w in snapshot.windows] == ["codex.primary"]
        assert snapshot.windows[0].window_secs == 604800

    def test_an_unused_sub_limit_is_still_shown(self, codex):
        body = deepcopy(CODEX_SUBLIMIT_BODY)
        body["additional_rate_limits"].append({
            "metered_feature": "other_feature",
            "limit_name": "Other",
            "rate_limit": body["additional_rate_limits"][0]["rate_limit"],
        })
        snapshot = codex.parse(body)
        unused = [w for w in snapshot.windows if w.used_pct == 0]
        assert [w.window_secs for w in unused] == [18000, 604800]
        assert all(w.qualifier == "Other" for w in unused)

    def test_main_five_hour_limit_is_preserved_alongside_spark(self, codex):
        body = {**CODEX_BODY, "additional_rate_limits": CODEX_SUBLIMIT_BODY["additional_rate_limits"]}
        assert codex.parse(body).windows == codex.parse(CODEX_BODY).windows

    @pytest.mark.parametrize("stale", [False, True])
    def test_existing_cache_also_excludes_spark(self, codex, stale):
        codex.cache.store("codex", CODEX_SUBLIMIT_BODY, now=1000)
        now = 1001
        if stale:
            codex.cache.mark_failure("codex", ttl=120, note="offline", now=1500)
            now = 1501
        with respx.mock:
            snapshot = codex.fetch(now=now)
        assert snapshot.status is (Status.STALE if stale else Status.CACHED)
        assert [w.key for w in snapshot.windows] == ["codex.primary"]

    def test_exhausted_spark_does_not_affect_display_or_alerts(self, codex):
        from tokentray.cli import _format_status

        body = deepcopy(CODEX_SUBLIMIT_BODY)
        now = 1_788_980_000
        clock = datetime.fromtimestamp(now, timezone.utc)
        body["rate_limit"]["primary_window"]["used_percent"] = 10
        for window in body["additional_rate_limits"][0]["rate_limit"].values():
            window.update(used_percent=100, reset_at=now + 300)
        view = build_view(codex.parse(body), clock)
        assert view.worst_remaining == 90
        assert view.tier == "green"
        assert [row.label for row in view.rows] == ["7 days"]
        assert "Spark" not in tooltip([view])
        assert "Spark" not in "\n".join(_format_status([view]))
        events = evaluate(
            [view], thresholds=[50, 25, 10], remind_before=[60, 30, 10],
            state=AlertState(seeded=True), now=now, clock=clock,
        )
        assert events == []

    def test_code_review_limit_gets_its_own_key(self, codex):
        body = dict(CODEX_SUBLIMIT_BODY)
        body["code_review_rate_limit"] = {
            "primary_window": {
                "used_percent": 4.0,
                "reset_at": 1_788_980_629,
                "limit_window_seconds": 604800,
            }
        }
        snapshot = codex.parse(body)
        review = [w for w in snapshot.windows if w.key.startswith("codex.code_review")]
        assert [w.key for w in review] == ["codex.code_review.primary"]
        assert review[0].qualifier == "Code Review"

    @pytest.mark.parametrize(
        "extra",
        [None, "nonsense", [], [None], [{}], [{"rate_limit": None}], [{"rate_limit": {}}]],
    )
    def test_a_malformed_sub_limit_block_is_skipped_not_raised(self, codex, extra):
        body = dict(CODEX_SUBLIMIT_BODY)
        body["additional_rate_limits"] = extra
        snapshot = codex.parse(body)
        assert [w.key for w in snapshot.windows] == ["codex.primary"]

    def test_a_sub_limit_without_a_feature_id_falls_back_to_its_name(self, codex):
        body = dict(CODEX_SUBLIMIT_BODY)
        body["additional_rate_limits"] = [
            {
                "limit_name": "Other-Model",
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 1.0,
                        "reset_at": 1_788_980_629,
                        "limit_window_seconds": 18000,
                    }
                },
            }
        ]
        snapshot = codex.parse(body)
        assert snapshot.windows[1].key == "codex.other_model.primary"

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
