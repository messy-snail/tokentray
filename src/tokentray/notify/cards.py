"""One alert card, rendered for Discord embeds and Slack Block Kit.

Both services show the same things - who raised the alert, which window, how
much is left, when it refills - so the choices about wording live here once and
each renderer only fits them to its service's markup and length limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.alerts import AlertEvent
from ..core.compute import TIER_COLORS
from ..core.i18n import t
from .formatting import provider_name

# Webhook.test() sends this; it is replaced by a translated card.
TEST_BODY = "Webhook notifications are working."
MARKERS = {"green": "🟢", "orange": "🟠", "red": "🔴"}
INFO_MARKER = "ℹ️"
SUMMARY_LIMIT = 240
_SLACK_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


@dataclass(frozen=True)
class Card:
    title: str
    author: str
    tier: str
    # One line for the channel preview and push notification.
    summary: str
    # The message, when the event is not about a single usage window.
    text: str = ""
    usage: bool = False
    label: str = ""
    marker: str = ""
    remaining: str = ""
    detail: str = ""
    # (name, value) pairs such as the refill time and pace.
    fields: tuple[tuple[str, str], ...] = ()


def plain_text(event: AlertEvent) -> str:
    """Body plus detail, for services that take a single block of text."""
    detail = event.detail
    if not detail and event.row is not None:
        detail = " · ".join(part for part in (event.row.refills, event.row.pace) if part)
    return f"{event.body}\n{detail}" if detail else event.body


def build_card(event: AlertEvent) -> Card:
    author = provider_name(event.provider) if event.provider else ""
    title = event.title
    if author and event.kind == "info" and title == t("fmt.notify_title", provider=author):
        title = t("card.status_title")
    if event.key == "test.usage":
        title = t("card.usage_title")
    elif event.kind in {"threshold", "reminder"}:
        title = t(f"card.{event.kind}_title")

    row = event.row
    if row is None:
        text = plain_text(event)
        if event.key == "test" and event.body == TEST_BODY:
            title, text = t("card.test_title"), t("card.test_body")
        summary = " · ".join(part for part in (title, author, text) if part)
        return Card(title=title, author=author, tier=event.tier, summary=_summary(summary), text=text)

    remaining = row.detail_status or row.remaining_text
    marker = INFO_MARKER if row.detail_status else MARKERS.get(row.tier, INFO_MARKER)
    # The view already includes the local reset time; keep it without
    # repeating the label in both the field name and its value.
    refills = next((item.value for item in row.details if item.key == "refills"), "")
    refills = refills or row.refills.removeprefix(t("label.refills") + " ")
    pace = row.pace.removeprefix(t("label.pace") + ": ")
    fields = tuple(
        (f"{icon} {t(f'label.{key}')}", value)
        for key, icon, value in (("refills", "🕒", refills), ("pace", "⚡", pace))
        if value.strip()
    )
    name = provider_name(event.provider)
    summary = f"{marker} {name} · {row.label} · {remaining}"
    if event.kind == "reminder":
        summary = f"{title} · {name} · {row.label} · {row.refills or remaining}"
    if event.detail:
        summary += f" · {event.detail}"
    return Card(
        title=title, author=author, tier=event.tier, summary=_summary(summary), usage=True,
        label=row.label, marker=marker, remaining=remaining, detail=event.detail, fields=fields,
    )


def discord_payload(card: Card) -> dict[str, Any]:
    embed: dict[str, Any] = {"color": int(TIER_COLORS.get(card.tier, TIER_COLORS["green"]).lstrip("#"), 16)}
    if card.author:
        embed["author"] = {"name": card.author[:256]}
    if card.usage:
        description = f"{card.label[:256]}\n**{card.marker} {card.remaining[:256]}**"
        if card.detail:
            description += f"\n\n{card.detail[:1024]}"
        if card.fields:
            embed["fields"] = [
                {"name": name, "value": value[:1024], "inline": True} for name, value in card.fields
            ]
    else:
        description = card.text[:4096]
    embed.update(title=card.title[:256], description=description)
    return {
        "username": "tokentray",
        "content": card.summary,
        "allowed_mentions": {"parse": []},
        "embeds": [embed],
    }


def slack_payload(card: Card) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [
        # Slack rejects the whole message over an empty header or section.
        {"type": "header", "text": {"type": "plain_text", "text": card.title[:150] or "tokentray", "emoji": True}},
    ]
    if card.author:
        blocks.append(_context(card.author))
    if card.usage:
        section: dict[str, Any] = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{_mrkdwn(card.label, 256)}\n*{card.marker} {_mrkdwn(card.remaining, 256)}*",
            },
        }
        if card.fields:
            section["fields"] = [
                {"type": "mrkdwn", "text": f"*{name}*\n{_mrkdwn(value, 1024)}"} for name, value in card.fields
            ]
        blocks.append(section)
        if card.detail:
            blocks.append(_context(card.detail))
    elif card.text.strip():
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": _mrkdwn(card.text, 3000)}})
    # The top-level text is what the push notification shows. Escaping it
    # keeps a provider message from reaching the channel as <!channel>.
    return {"text": _mrkdwn(card.summary, 3000), "blocks": blocks}


def _context(text: str) -> dict[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": _mrkdwn(text, 1024)}]}


def _mrkdwn(text: str, limit: int) -> str:
    """Escape Slack's control characters without cutting an entity in half."""
    pieces = [_SLACK_ESCAPES.get(char, char) for char in text]
    if sum(map(len, pieces)) <= limit:
        return "".join(pieces)
    kept: list[str] = []
    size = 0
    for piece in pieces:
        if size + len(piece) > limit - 1:
            break
        kept.append(piece)
        size += len(piece)
    return "".join(kept) + "…"


def _summary(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SUMMARY_LIMIT else text[: SUMMARY_LIMIT - 1] + "…"
