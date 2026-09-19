from datetime import datetime, timedelta, timezone

import pytest

from tokentray.core import i18n
from tokentray.core.alerts import AlertEvent, AlertState, evaluate
from tokentray.core.models import Snapshot, Status, UsageWindow
from tokentray.core.view import build_view
from tokentray.notify.cards import build_card, discord_payload, slack_payload

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


def slack(event):
    return slack_payload(build_card(event))


@pytest.mark.parametrize("language", ["en", "ko"])
@pytest.mark.parametrize("kind", ["threshold", "reminder"])
def test_usage_card_matches_discord_layout(language, kind):
    event = usage_event(kind, language)
    row = event.row
    payload = slack(event)
    header, author, section = payload["blocks"]
    assert header == {
        "type": "header",
        "text": {"type": "plain_text", "text": i18n.t(f"card.{kind}_title"), "emoji": True},
    }
    assert author == {"type": "context", "elements": [{"type": "mrkdwn", "text": "Claude Code"}]}
    # Slack bolds with single asterisks; Discord's ** would show literally.
    assert section["text"] == {"type": "mrkdwn", "text": f"{row.label}\n*🟠 {row.remaining_text}*"}
    refills = next(item.value for item in row.details if item.key == "refills")
    assert section["fields"] == [
        {"type": "mrkdwn", "text": f"*🕒 {i18n.t('label.refills')}*\n{refills}"},
        {"type": "mrkdwn", "text": f"*⚡ {i18n.t('label.pace')}*\n{row.stats.pace}x"},
    ]
    # One summary line for both services' push notifications.
    assert payload["text"] == discord_payload(build_card(event))["content"]


def test_korean_usage_card_is_not_left_in_english():
    payload = slack(usage_event("threshold", "ko"))
    assert payload["blocks"][0]["text"]["text"] == "⚠️ 사용량 경고"
    assert "남음" in payload["blocks"][2]["text"]["text"]


def test_status_only_row_has_no_fields_or_fake_percentage():
    event = usage_event("threshold")
    event.row.details = []
    event.row.refills = ""
    event.row.pace = ""
    event.row.detail_status = "Reset pending"
    section = slack(event)["blocks"][2]
    assert "fields" not in section
    assert section["text"]["text"].endswith("*ℹ️ Reset pending*")
    assert "25%" not in section["text"]["text"]


@pytest.mark.parametrize("language", ["en", "ko"])
def test_connection_notice_keeps_the_actionable_message(language):
    i18n.set_language(language)
    view = build_view(Snapshot(provider="codex", status=Status.UNAUTHORIZED), NOW)
    event = evaluate(
        [view], thresholds=[25], remind_before=[], state=AlertState(seeded=True),
        now=NOW.timestamp(), clock=NOW,
    )[0]
    header, author, section = slack(event)["blocks"]
    assert header["text"]["text"] == i18n.t("card.status_title")
    assert author["elements"][0]["text"] == "Codex"
    assert section["text"]["text"] == event.body


def test_mentions_and_markup_in_messages_are_escaped():
    event = AlertEvent(
        kind="info", key="summary", title="<!channel> & co", body="<!channel> <@U123> a&b",
        provider="codex", detail="x > y",
    )
    payload = slack(event)
    section = payload["blocks"][2]["text"]["text"]
    assert section == "&lt;!channel&gt; &lt;@U123&gt; a&amp;b\nx &gt; y"
    assert "<!channel>" not in payload["text"]
    # A header is plain text, so Slack shows it as written without parsing.
    assert payload["blocks"][0]["text"]["text"] == "<!channel> & co"


@pytest.mark.parametrize("with_row", [False, True])
def test_long_messages_fit_slack_limits(with_row):
    event = usage_event("threshold")
    event.title = "T" * 5000
    event.provider = "P" * 5000
    event.body = "&" * 5000
    event.detail = "D" * 5000
    if with_row:
        event.row.label = "<" * 5000
        event.row.remaining_text = "R" * 5000
        event.row.details = []
        event.row.refills = "F" * 5000
        event.row.pace = "S" * 5000
    else:
        event.row = None
    payload = slack(event)
    assert len(payload["text"]) <= 3000
    header = payload["blocks"][0]["text"]["text"]
    assert len(header) <= 150
    for block in payload["blocks"][1:]:
        texts = [block["text"]["text"]] if "text" in block else []
        texts += [element["text"] for element in block.get("elements", [])]
        texts += [field["text"] for field in block.get("fields", [])]
        for text in texts:
            assert len(text) <= 3000
            # Truncation must never split an escape into "&am".
            assert not text.rstrip("…").endswith(("&", "&a", "&am", "&amp", "&l", "&lt", "&g", "&gt"))
        for field in block.get("fields", []):
            assert len(field["text"]) <= 2000


def test_connection_test_is_translated():
    i18n.set_language("ko")
    event = AlertEvent(kind="info", key="test", title="tokentray",
                       body="Webhook notifications are working.", tier="green")
    blocks = slack(event)["blocks"]
    assert [block["type"] for block in blocks] == ["header", "section"]
    assert blocks[0]["text"]["text"] == "✅ 연결 테스트"
    assert blocks[1]["text"]["text"] == "웹훅 알림이 정상적으로 연결됐어요."
