from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from email.utils import formatdate

import httpx
import pytest
import respx

from tokentray.core.cache import Cache
from tokentray.core.config import Config
from tokentray.core.models import Status
from tokentray.providers.claude import USAGE_URL, ClaudeProvider
from tokentray.providers.retry import rate_limit_delay

BODY = {"five_hour": {"utilization": 20, "resets_at": "2030-01-01T00:00:00Z"}}


@pytest.mark.parametrize("interval", [30, 120, 180, 300, 600])
def test_user_polling_interval_is_preserved(interval):
    config = Config({"poll_interval": interval})
    assert config.poll_interval == interval
    assert config.cache_ttl == interval - 10
    assert rate_limit_delay(None, 1000, interval, 0)[0] == max(interval, 300)


@pytest.mark.parametrize("header,expected", [
    ("3203", 3203), ("7200", 7200), ("10", 120),
    (formatdate(1500, usegmt=True), 500),
    (None, 300), ("", 300), ("0", 300), ("-1", 300), ("1.5", 300),
    ("private-token", 300), (formatdate(900, usegmt=True), 300), ("9" * 400, 300),
])
def test_retry_after_forms(header, expected):
    assert rate_limit_delay(header, 1000, 120, 0)[0] == expected


def test_backoff_sequence_and_long_user_interval():
    assert [rate_limit_delay(None, 1000, 120, n)[0] for n in range(7)] == [300, 600, 1200, 2400, 3600, 3600, 3600]
    assert rate_limit_delay(None, 1000, 7200, 10000)[0] == 7200


@pytest.fixture
def provider(config, cache, claude_credentials):
    instance = ClaudeProvider(config, cache)
    yield instance
    instance.close()


@pytest.mark.parametrize("cached", [False, True])
def test_rate_limit_blocks_forced_fetch_and_survives_restart(provider, cache, cached):
    if cached:
        cache.store("claude", BODY, now=900)
    with respx.mock:
        route = respx.get(USAGE_URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "3203"}))
        failed = provider.fetch(force=True, now=1000)
        assert failed.status is (Status.STALE if cached else Status.RATE_LIMITED)
        assert failed.failure_kind == "rate_limited"
        assert failed.retry_at == 4203
        assert not failed.request_skipped
        restored = ClaudeProvider(Config({"poll_interval": 30}), cache)
        try:
            for force in (False, True):
                waiting = restored.fetch(force=force, now=4202)
                assert waiting.failure_kind == "rate_limited"
                assert waiting.request_skipped
                assert waiting.retry_at == 4203
            assert route.call_count == 1
            route.mock(return_value=httpx.Response(200, json=BODY))
            assert restored.fetch(force=True, now=4203).status is Status.OK
        finally:
            restored.close()
    entry = cache.load("claude")
    assert entry.rate_limit_count == 0
    assert entry.rate_limit_until == 0
    assert not entry.failure_kind


def test_repeated_429_increases_delay_until_success(provider, cache):
    now = 1000
    with respx.mock:
        route = respx.get(USAGE_URL).mock(return_value=httpx.Response(429))
        for delay in (300, 600, 1200, 2400, 3600, 3600):
            snapshot = provider.fetch(force=True, now=now)
            assert snapshot.retry_at == now + delay
            now += delay
        route.mock(return_value=httpx.Response(200, json=BODY))
        provider.fetch(force=True, now=now)
        assert cache.load("claude").rate_limit_count == 0
        route.mock(return_value=httpx.Response(429))
        assert provider.fetch(force=True, now=now + 30).retry_at == now + 330


def test_force_and_other_instances_obey_thirty_second_gate(provider, cache, config):
    other = ClaudeProvider(config, cache)
    try:
        with respx.mock:
            route = respx.get(USAGE_URL).mock(return_value=httpx.Response(200, json=BODY))
            assert provider.fetch(now=1000).status is Status.OK
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: other.fetch(force=True, now=1001), range(5)))
            assert all(s.status is Status.CACHED and s.request_skipped for s in results)
            assert route.call_count == 1
            assert other.fetch(force=True, now=1030).status is Status.OK
            assert route.call_count == 2
    finally:
        other.close()


def test_connection_error_is_never_reported_as_rate_limit(provider):
    with respx.mock:
        respx.get(USAGE_URL).mock(side_effect=httpx.ConnectError("private text"))
        for now in (1000, 1001, 1040):
            snapshot = provider.fetch(now=now)
            assert snapshot.failure_kind == "connection"
            assert snapshot.status is Status.ERROR


def test_legacy_cache_loads_with_default_pacing_fields(tmp_path):
    (tmp_path / "claude.json").write_text(json.dumps({
        "body": BODY, "fetched_at": 1000, "backoff_until": 0, "note": "",
    }), encoding="utf-8")
    entry = Cache(tmp_path).load("claude")
    assert entry.last_attempt == entry.rate_limit_until == entry.rate_limit_count == 0
    assert entry.failure_kind == ""


def test_duplicate_gate_preserves_auth_failure_without_showing_old_data(provider, cache):
    cache.store("claude", BODY, now=900)
    with respx.mock:
        route = respx.get(USAGE_URL).mock(return_value=httpx.Response(401))
        assert provider.fetch(force=True, now=1000).status is Status.UNAUTHORIZED
        duplicate = provider.fetch(force=True, now=1001)
        assert duplicate.status is Status.UNAUTHORIZED
        assert not duplicate.windows
        assert route.call_count == 1


def test_claude_wait_does_not_block_codex_and_notification_preview(
    qapp, provider, config, cache, codex_credentials, monkeypatch,
):
    from types import SimpleNamespace

    from tokentray import providers
    from tokentray.polling import PollWorker
    from tokentray.providers.codex import USAGE_URL as CODEX_URL
    from tokentray.providers.codex import CodexProvider

    codex = CodexProvider(config, cache)
    now = [1000]
    monkeypatch.setattr(providers, "build_providers", lambda *a: [
        SimpleNamespace(id=p.id, fetch=lambda force, p=p: p.fetch(force=force, now=now[0]))
        for p in (provider, codex)
    ])
    worker = PollWorker(config)
    previews = []
    completions = []
    worker.test_finished.connect(previews.append)
    worker.refresh_finished.connect(completions.append)
    try:
        with respx.mock:
            claude_route = respx.get(USAGE_URL).mock(return_value=httpx.Response(429))
            codex_route = respx.get(CODEX_URL).mock(return_value=httpx.Response(200, json={
                "rate_limit": {"primary_window": {"used_percent": 20, "limit_window_seconds": 18000}},
            }))
            worker._run(True)
            now[0] = 1030
            worker._run(True)
            worker._run_test()
            assert claude_route.call_count == 1
            assert codex_route.call_count == 2
            assert completions[-1].providers[0].outcome == "waiting"
            assert completions[-1].providers[1].outcome == "done"
            assert previews[0][0].failure_kind == "rate_limited"
    finally:
        codex.close()
