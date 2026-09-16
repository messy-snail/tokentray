from datetime import datetime, timedelta, timezone

import pytest

from tokentray.core import i18n
from tokentray.core.alerts import AlertState, evaluate
from tokentray.core.compute import TIER_COLORS
from tokentray.core.models import Snapshot, Status, UsageWindow
from tokentray.core.view import build_view
from tokentray.notify.webhook import Webhook, _discord_payload, _slack_payload

NOW = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)


def usage_event(kind, language="en"):
    i18n.set_language(language)
    view = build_view(
        Snapshot(
            provider="claude", status=Status.OK,
            windows=[UsageWindow(
                key="claude.5h", used_pct=75,
                resets_at=NOW + timedelta(minutes=30), window_secs=18000,
            )],
        ), NOW,
    )
    events = evaluate(
        [view], thresholds=[25], remind_before=[30],
        state=AlertState(seeded=True, last_used={"claude.5h": 75}),
        now=NOW.timestamp(), clock=NOW,
    )
    return next(event for event in events if event.kind == kind)


@pytest.mark.parametrize("language", ["en", "ko"])
@pytest.mark.parametrize("kind", ["threshold", "reminder"])
def test_usage_card_separates_identity_usage_and_details(language, kind):
    event = usage_event(kind, language)
    row = event.row
    payload = _discord_payload(event)
    embed = payload["embeds"][0]
    assert embed["author"] == {"name": "Claude Code"}
    assert embed["title"] == i18n.t(f"discord.{kind}_title")
    assert embed["description"] == f"{row.label}\n**🟠 {row.remaining_text}**"
    refills = next(item.value for item in row.details if item.key == "refills")
    assert embed["fields"] == [
        {"name": f"🕒 {i18n.t('label.refills')}", "value": refills, "inline": True},
        {"name": f"⚡ {i18n.t('label.pace')}", "value": f"{row.stats.pace}x", "inline": True},
    ]
    assert embed["color"] == int(TIER_COLORS[event.tier].lstrip("#"), 16)
    assert payload["allowed_mentions"] == {"parse": []}
    assert "footer" not in embed
    assert row.refills not in embed["description"]
    assert embed["description"].count("25%") == 1
    if kind == "threshold":
        assert payload["content"] == f"🟠 Claude Code · {row.label} · {row.remaining_text}"
    else:
        assert i18n.t("discord.reminder_title") in payload["content"]
        assert row.refills in payload["content"]


def test_missing_optional_fields_are_omitted_and_status_is_not_a_fake_percentage():
    event = usage_event("threshold")
    event.row.details = []
    event.row.refills = ""
    event.row.pace = ""
    event.row.detail_status = "Reset pending"
    embed = _discord_payload(event)["embeds"][0]
    assert "fields" not in embed
    assert "Reset pending" in embed["description"]
    assert "ℹ️" in embed["description"]
    assert "25%" not in embed["description"]
    assert "ℹ️" in _discord_payload(event)["content"]
    assert "25%" not in _discord_payload(event)["content"]


@pytest.mark.parametrize("language", ["en", "ko"])
def test_legacy_row_without_details_keeps_reset_time(language):
    event = usage_event("reminder", language)
    event.row.details = []
    embed = _discord_payload(event)["embeds"][0]
    assert embed["fields"][0]["value"] == event.row.refills.removeprefix(
        i18n.t("label.refills") + " "
    )


@pytest.mark.parametrize("language", ["en", "ko"])
def test_connection_notice_preserves_actionable_message(language):
    i18n.set_language(language)
    view = build_view(Snapshot(provider="codex", status=Status.UNAUTHORIZED), NOW)
    event = evaluate(
        [view], thresholds=[25], remind_before=[], state=AlertState(seeded=True),
        now=NOW.timestamp(), clock=NOW,
    )[0]
    event.detail = "@everyone <@123>"
    payload = _discord_payload(event)
    embed = payload["embeds"][0]
    assert embed["title"] == i18n.t("discord.status_title")
    assert embed["author"] == {"name": "Codex"}
    assert embed["description"] == f"{event.body}\n{event.detail}"
    assert "fields" not in embed
    assert payload["allowed_mentions"] == {"parse": []}
    assert event.body in payload["content"]
    assert "\n" not in payload["content"]


@pytest.mark.parametrize("language", ["en", "ko"])
def test_webhook_test_is_localized_only_for_discord(language, monkeypatch):
    i18n.set_language(language)
    events = []
    webhook = Webhook(enabled=False, kind="discord")
    monkeypatch.setattr(webhook, "_enqueue", lambda event, callback: events.append(event))
    webhook.test(lambda result: None)
    event = events[0]
    embed = _discord_payload(event)["embeds"][0]
    assert embed["title"] == i18n.t("discord.test_title")
    assert embed["description"] == i18n.t("discord.test_body")
    assert "fields" not in embed
    assert "author" not in embed
    assert _slack_payload(event)["text"] == "tokentray: Webhook notifications are working."
    assert i18n.t("discord.test_body") in _discord_payload(event)["content"]


@pytest.mark.parametrize("with_row", [False, True])
def test_long_messages_fit_discord_limits(with_row):
    event = usage_event("threshold")
    event.title = "T" * 5000
    event.provider = "P" * 5000
    event.body = "B" * 5000
    event.detail = "D" * 5000
    if with_row:
        event.row.label = "L" * 5000
        event.row.remaining_text = "R" * 5000
        event.row.details = []
        event.row.refills = "F" * 5000
        event.row.pace = "S" * 5000
    else:
        event.row = None
    payload = _discord_payload(event)
    assert len(payload["content"]) <= 240
    assert payload["content"].endswith("…")
    embed = payload["embeds"][0]
    assert len(embed["title"]) <= 256
    assert len(embed["author"]["name"]) <= 256
    assert len(embed["description"]) <= 4096
    total = len(embed["title"] + embed["description"] + embed["author"]["name"])
    for field in embed.get("fields", []):
        assert 0 < len(field["name"]) <= 256
        assert 0 < len(field["value"]) <= 1024
        total += len(field["name"] + field["value"])
    assert total <= 6000


def test_custom_detail_is_preserved_without_changing_slack():
    event = usage_event("threshold")
    event.detail = "Additional context"
    embed = _discord_payload(event)["embeds"][0]
    assert embed["description"].endswith("\n\nAdditional context")
    assert _slack_payload(event)["blocks"][1]["text"]["text"] == f"{event.body}\nAdditional context"


@pytest.mark.parametrize("tier,marker", [("green", "🟢"), ("orange", "🟠"), ("red", "🔴")])
def test_remaining_marker_follows_row_status(tier, marker):
    event = usage_event("threshold")
    event.row.tier = tier
    assert f"**{marker} " in _discord_payload(event)["embeds"][0]["description"]


@pytest.mark.parametrize("language", ["en", "ko"])
def test_preview_has_current_usage_title_only_on_discord(language):
    event = usage_event("threshold", language)
    event.kind = "info"
    event.key = "test.usage"
    event.title = i18n.t("test.title")
    assert _discord_payload(event)["embeds"][0]["title"] == i18n.t("discord.usage_title")
    assert _slack_payload(event)["blocks"][0]["text"]["text"] == event.title
