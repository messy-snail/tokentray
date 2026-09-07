"""Presentation model shared by the CLI, the tray tooltip and the detail panel.

Snapshots carry raw numbers; widgets need localized strings. Doing that
translation once, here, keeps the three surfaces from drifting apart and keeps
Qt out of anything that needs testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import compute, i18n
from .models import Snapshot, Status

PROVIDER_NAMES = {"claude": "Claude Code", "codex": "Codex"}
PROVIDER_ABBR = {"claude": "CC", "codex": "CX"}


@dataclass
class WindowRow:
    """One rendered rate-limit window."""

    key: str
    label: str
    remaining: int
    remaining_text: str
    tier: str
    color: str
    bar: str
    refills: str
    burns: str
    pace: str
    pace_icon: str
    stats: compute.WindowStats


@dataclass
class ProviderView:
    provider: str
    title: str
    status: Status
    message: str
    source: str
    rows: list[WindowRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def worst_remaining(self) -> int | None:
        """Lowest remaining across windows — what the tray icon colour follows."""
        if not self.rows:
            return None
        return min(row.remaining for row in self.rows)

    @property
    def tier(self) -> str:
        worst = self.worst_remaining
        return compute.tier_for(worst) if worst is not None else compute.TIER_RED


def build_view(snapshot: Snapshot, now: datetime | None = None) -> ProviderView:
    now = now or datetime.now(timezone.utc)
    name = PROVIDER_NAMES.get(snapshot.provider, snapshot.provider)
    title = i18n.t("fmt.plan", provider=name, plan=snapshot.plan) if snapshot.plan else name

    view = ProviderView(
        provider=snapshot.provider,
        title=title,
        status=snapshot.status,
        message=status_message(snapshot),
        source=source_label(snapshot),
    )
    if not snapshot.status.has_data:
        return view

    for window in snapshot.windows:
        stats = compute.derive(window, now)
        label = i18n.t(window.label_key, **window.label_args)
        # A stale reading whose window already reset is not "62% left", it is
        # unknown-but-probably-refilled. Say that rather than lie precisely.
        if snapshot.window_reset_pending and stats.secs_until_reset is not None and stats.secs_until_reset <= 0:
            remaining_text = "~0%"
        else:
            remaining_text = i18n.t("fmt.remaining", pct=stats.remaining_int)
        view.rows.append(
            WindowRow(
                key=window.key,
                label=label,
                remaining=stats.remaining_int,
                remaining_text=remaining_text,
                tier=stats.tier,
                color=stats.color,
                bar=compute.progress_bar(stats.remaining),
                refills=_refills_text(stats, now),
                burns=_burns_text(stats),
                pace=i18n.t("fmt.pace", pace=stats.pace) if stats.pace is not None else "",
                pace_icon=compute.pace_icon(stats.pace),
                stats=stats,
            )
        )

    view.notes = _notes(snapshot)
    return view


def _refills_text(stats: compute.WindowStats, now: datetime) -> str:
    if stats.secs_until_reset is not None and stats.secs_until_reset <= 0:
        return i18n.t("status.window_reset")
    duration = compute.format_duration(stats.secs_until_reset)
    if not duration:
        return ""
    local = compute.format_local_reset(stats.window.resets_at, now)
    text = i18n.t("fmt.refills", dur=duration)
    return f"{text} ({local})" if local else text


def _burns_text(stats: compute.WindowStats) -> str:
    if stats.exhausted:
        return ""
    duration = compute.format_duration(stats.burnout_secs)
    return i18n.t("fmt.burns", dur=duration) if duration else ""


def _notes(snapshot: Snapshot) -> list[str]:
    notes: list[str] = []
    extra = snapshot.extra
    if extra is not None:
        if extra.enabled and extra.used is not None and extra.limit is not None:
            value = i18n.t(
                "fmt.extra_usage",
                used=f"{extra.used:.2f}",
                limit=f"{extra.limit:.2f}",
                currency=extra.currency,
            )
        else:
            value = i18n.t("label.extra_off")
        notes.append(f"{i18n.t('label.extra_usage')}: {value}")
    credits = snapshot.credits
    if credits is not None:
        value = (
            i18n.t("label.credits_unlimited")
            if credits.unlimited
            else f"{credits.balance:g}" if credits.balance is not None else ""
        )
        if value:
            notes.append(f"{i18n.t('label.credits')}: {value}")
    return notes


def status_message(snapshot: Snapshot) -> str:
    """One line explaining a non-OK status, in the user's language."""
    provider = snapshot.provider
    mapping = {
        Status.NOT_CONFIGURED: f"status.not_configured_{provider}",
        Status.EXPIRED: f"status.expired_{provider}",
        Status.UNAUTHORIZED: f"status.expired_{provider}",
        Status.SCHEMA_CHANGED: "status.schema_changed",
        Status.RATE_LIMITED: "status.rate_limited",
    }
    key = mapping.get(snapshot.status)
    if key:
        return i18n.t(key)
    if snapshot.status is Status.ERROR:
        detail = f" ({snapshot.detail})" if snapshot.detail else ""
        return f"{i18n.t('status.api_error')}{detail}"
    if not snapshot.windows and snapshot.status.has_data:
        return i18n.t("status.no_data")
    return ""


def source_label(snapshot: Snapshot) -> str:
    if snapshot.status is Status.OK:
        return i18n.t("status.live")
    if snapshot.status is Status.CACHED:
        return f"{i18n.t('status.cached')}{f' ({snapshot.detail})' if snapshot.detail else ''}"
    if snapshot.status is Status.STALE:
        return f"{i18n.t('status.stale')}{f' - {snapshot.detail}' if snapshot.detail else ''}"
    return snapshot.detail or ""


def tooltip(views: list[ProviderView], limit: int = 127) -> str:
    """Compact one-line summary. Windows truncates tray tooltips at 128 chars."""
    parts: list[str] = []
    for view in views:
        abbr = PROVIDER_ABBR.get(view.provider, view.provider)
        if view.rows:
            inner = " ".join(f"{_short_label(row)} {row.remaining}%" for row in view.rows[:3])
            parts.append(f"{abbr} {inner}")
        elif view.message:
            parts.append(f"{abbr} {view.message}")
    text = " | ".join(parts) or "tokentray"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _short_label(row: WindowRow) -> str:
    """Abbreviate a window label for the tooltip (``5h``, ``7d``, ``Opus``)."""
    key = row.key.rsplit(".", 1)[-1]
    return {"5h": "5h", "7d": "7d", "7d_opus": "Opus", "7d_sonnet": "Sonnet"}.get(
        key, row.label.replace("Codex ", "")
    )
