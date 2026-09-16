from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from typer.testing import CliRunner

from tokentray.cli import app
from tokentray.core import i18n
from tokentray.core.config import Config
from tokentray.core.models import Snapshot, Status, UsageWindow
from tokentray.core.view import build_view

URL = "https://discord.com/api/webhooks/123/test"


@pytest.fixture
def preview_setup(isolated_config, monkeypatch):
    config = Config.load()
    config.set("webhook.kind", "discord")
    config.set("webhook.url", URL)
    config.set("language", "ko")
    config.save()
    now = datetime.now(timezone.utc)
    views = []
    calls = []

    def collect(config, *, force):
        calls.append(force)
        return views

    monkeypatch.setattr("tokentray.notify.preview.collect_views", collect)

    def no_state(*args, **kwargs):
        pytest.fail("A manual preview must not evaluate or persist automatic alerts")

    monkeypatch.setattr("tokentray.core.alerts.evaluate", no_state)
    monkeypatch.setattr("tokentray.core.alerts.AlertState.to_dict", no_state)
    views.append(build_view(Snapshot(
        provider="claude", status=Status.OK,
        windows=[UsageWindow(
            key=f"claude.{hours}h", used_pct=20,
            resets_at=now + timedelta(minutes=30), window_secs=hours * 3600,
        ) for hours in (5, 168)],
    ), now))
    return views, calls


def test_usage_command_delivers_real_cards_even_when_automatic_webhook_is_disabled(preview_setup, webhook_payload):
    views, calls = preview_setup
    with respx.mock:
        route = respx.post(URL).mock(return_value=httpx.Response(200, json={}))
        result = CliRunner().invoke(app, ["webhook", "test", "--usage"])
    assert result.exit_code == 0, result.output
    assert calls == [True]
    assert route.call_count == 2
    assert "2 cards" in result.output
    for call, row in zip(route.calls, views[0].rows):
        embed = webhook_payload(call.request)["embeds"][0]
        assert embed["title"] == "📊 현재 사용량"
        assert row.remaining_text in embed["description"]
        assert row.label in embed["description"]
        assert len(embed["fields"]) == 2


def test_default_connection_test_does_not_fetch_usage(preview_setup, webhook_payload):
    _, calls = preview_setup
    with respx.mock:
        route = respx.post(URL).mock(return_value=httpx.Response(200, json={}))
        result = CliRunner().invoke(app, ["webhook", "test"])
    assert result.exit_code == 0
    assert calls == []
    embed = webhook_payload(route.calls[0].request)["embeds"][0]
    assert embed["description"] == "웹훅 알림이 정상적으로 연결됐어요."
    assert "fields" not in embed


@pytest.mark.parametrize("status", [Status.STALE, Status.CACHED, Status.ERROR])
def test_unavailable_or_old_data_is_labelled(preview_setup, status, webhook_payload):
    views, _ = preview_setup
    views[0].status = status
    with respx.mock:
        route = respx.post(URL).mock(return_value=httpx.Response(200, json={}))
        result = CliRunner().invoke(app, ["webhook", "test", "--usage"])
    assert result.exit_code == 0
    embed = webhook_payload(route.calls[0].request)["embeds"][0]
    if status.has_data:
        assert "이전 데이터" in embed["description"]
    else:
        assert route.call_count == 1
        assert i18n.t("status.no_data") in embed["description"]
        assert "fields" not in embed


def test_missing_destination_does_not_fetch(isolated_config, monkeypatch):
    monkeypatch.setattr("tokentray.notify.preview.collect_views", lambda *a, **k: pytest.fail("Must not fetch"))
    result = CliRunner().invoke(app, ["webhook", "test", "--usage"])
    assert result.exit_code == 1
    assert "Configure a webhook" in result.output


def test_no_enabled_providers(preview_setup):
    views, _ = preview_setup
    views.clear()
    with respx.mock:
        result = CliRunner().invoke(app, ["webhook", "test", "--usage"])
    assert result.exit_code == 1
    assert "No enabled providers" in result.output


def test_delivery_failure_is_reported_and_stops(preview_setup):
    with respx.mock:
        route = respx.post(URL).mock(return_value=httpx.Response(403))
        result = CliRunner().invoke(app, ["webhook", "test", "--usage"])
    assert result.exit_code == 1
    assert "HTTP 403" in result.output
    assert route.call_count == 1
