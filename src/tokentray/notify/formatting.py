"""Shared alert presentation for local and remote notification channels."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..core.alerts import AlertEvent
from ..core.i18n import t
from ..core.models import Status
from ..core.view import PROVIDER_NAMES, PROVIDER_ORDER, ProviderView


@dataclass(frozen=True)
class AlertSummary:
    title: str
    body: str
    detail: str


def provider_name(provider: str | None) -> str:
    if not provider:
        return "tokentray"
    return PROVIDER_NAMES.get(provider, provider)


def usage_preview(views: list[ProviderView], *, disabled: set[str]) -> AlertSummary:
    """Describe fetched quota without changing automatic alert state."""
    contents = usage_preview_contents(views, disabled=disabled)
    body = "\n".join(f"{provider_name(p)}: {content}" for p, content in contents.items())
    return AlertSummary(title=t("test.title"), body=body, detail="")


def usage_preview_contents(views: list[ProviderView], *, disabled: set[str]) -> dict[str, str]:
    """Service-specific text for both native summaries and custom cards."""
    by_provider = {view.provider: view for view in views}
    contents = {}
    for provider in PROVIDER_ORDER:
        view = by_provider.get(provider)
        if provider in disabled:
            content = t("test.disabled")
        elif view is None:
            content = t("status.no_data")
        elif view.status.has_data and view.rows:
            content = ", ".join(
                f"{row.label} {row.detail_status or row.remaining_text}" for row in view.rows
            )
            if view.status in (Status.CACHED, Status.STALE):
                content = f"{t('test.previous_data')}: {content}"
        else:
            content = view.message or t("status.no_data")
        contents[provider] = content
    return contents


def usage_preview_events(views: list[ProviderView]) -> list[AlertEvent]:
    """Build manual webhook previews without evaluating automatic alert state."""
    events = []
    for view in views:
        previous = t("test.previous_data") if view.status in (Status.CACHED, Status.STALE) else ""
        for row in view.rows if view.status.has_data else []:
            events.append(AlertEvent(
                kind="info", key="test.usage", title=t("test.title"),
                body=f"{provider_name(view.provider)} · {row.label}: {row.detail_status or row.remaining_text}",
                provider=view.provider, row=row, tier=row.tier, detail=previous,
            ))
        if not view.status.has_data or not view.rows:
            events.append(AlertEvent(
                kind="info", key="test.usage", title=t("test.title"),
                body=f"{provider_name(view.provider)}: {view.message or t('status.no_data')}",
                provider=view.provider,
            ))
    return events


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
