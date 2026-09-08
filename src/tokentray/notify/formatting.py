"""Shared alert presentation for local and remote notification channels."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..core.alerts import AlertEvent
from ..core.i18n import t
from ..core.view import PROVIDER_NAMES


@dataclass(frozen=True)
class AlertSummary:
    title: str
    body: str
    detail: str


def provider_name(provider: str | None) -> str:
    if not provider:
        return "tokentray"
    return PROVIDER_NAMES.get(provider, provider)


def summarize(events: list[AlertEvent]) -> AlertSummary:
    """Collapse a burst while preserving which provider raised each alert."""
    counts = Counter(event.provider for event in events if event.provider)
    names = [provider_name(provider) for provider in ("claude", "codex") if counts[provider]]
    names.extend(provider_name(provider) for provider in counts if provider not in {"claude", "codex"})
    title = "tokentray" + (f" · {' + '.join(names)}" if names else "")
    breakdown = ", ".join(
        f"{provider_name(provider)} {count}" for provider, count in counts.items()
    )
    body = t("fmt.summary", n=len(events), providers=breakdown)
    details: list[str] = []
    for event in events:
        label = provider_name(event.provider)
        if event.row is not None:
            details.append(f"{label} {event.row.label} {event.row.remaining}%")
        else:
            details.append(f"{label}: {event.body}")
    return AlertSummary(title=title, body=body, detail=" · ".join(details)[:220])
