"""When to speak up, and when to stay quiet.

Pure functions over a plain state dict: no timers, no Qt, no clock of its own.
That makes every rule below directly testable, which matters because the failure
modes here are all about *not* firing — a monitor that cries wolf on restart, or
during a burst, gets muted by its user within a day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from . import i18n
from .compute import format_local_reset
from .view import PROVIDER_NAMES, ProviderView, WindowRow

THRESHOLD_ARMED = 100
REMIND_ARMED = 999

# Smallest usage increase between two polls that counts as "still working".
# Anything above measurement noise means they are at the keyboard right now, and
# telling them their quota is about to refill is noise rather than news.
ACTIVE_DELTA = 0.05

# Fallback activity signal for the first poll after a restart, when there is no
# previous sample to diff against. Note this can only ever trigger early in a
# window: reaching 1.3x requires at least 23% of the window still to run, so for
# the default 60/30/10-minute reminders it never fires on its own. The reference
# implementation relied on this check alone, which made its "skip the nudge if
# you are actively coding" rule inert in practice.
ACTIVE_PACE = 1.3

Kind = Literal["threshold", "reminder", "info"]
Priority = Literal["default", "high", "urgent"]


@dataclass
class AlertEvent:
    kind: Kind
    key: str
    title: str
    body: str
    tier: str = "orange"
    priority: Priority = "default"
    row: WindowRow | None = None
    provider: str | None = None
    detail: str = ""


@dataclass
class AlertState:
    """Persisted between runs so alerts survive a restart without repeating."""

    threshold: dict[str, int] = field(default_factory=dict)
    remind: dict[str, int] = field(default_factory=dict)
    last_used: dict[str, float] = field(default_factory=dict)
    notified_status: dict[str, str] = field(default_factory=dict)
    paused_until: float = 0.0
    seeded: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AlertState":
        data = data or {}
        return cls(
            threshold={str(k): int(v) for k, v in _dict(data.get("threshold")).items()},
            remind={str(k): int(v) for k, v in _dict(data.get("remind")).items()},
            last_used={str(k): _float(v) for k, v in _dict(data.get("last_used")).items()},
            notified_status={str(k): str(v) for k, v in _dict(data.get("notified_status")).items()},
            paused_until=_float(data.get("paused_until")),
            seeded=bool(data.get("seeded", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "remind": self.remind,
            "last_used": self.last_used,
            "notified_status": self.notified_status,
            "paused_until": self.paused_until,
            "seeded": self.seeded,
        }

    def is_paused(self, now: float) -> bool:
        return now < self.paused_until


def evaluate(
    views: Iterable[ProviderView],
    *,
    thresholds: list[int],
    remind_before: list[int],
    state: AlertState,
    now: float,
    clock: datetime | None = None,
) -> list[AlertEvent]:
    """Advance ``state`` for this poll and return the alerts to deliver.

    ``state`` is mutated in place; the caller persists it. Alerts are suppressed
    while paused, but the state still advances, so un-pausing does not release a
    backlog of stale warnings.
    """
    views = list(views)
    clock = clock or datetime.now(timezone.utc)
    thresholds = sorted({int(t) for t in thresholds}, reverse=True)
    remind_before = sorted({int(m) for m in remind_before}, reverse=True)

    info: list[AlertEvent] = []
    usage: list[AlertEvent] = []

    for view in views:
        info.extend(_status_events(view, state))
        for row in view.rows:
            active = _is_active(row, state)
            usage.extend(_threshold_events(row, thresholds, state, view.provider))
            usage.extend(
                _reminder_events(row, remind_before, state, clock, active, view.provider)
            )
            state.last_used[row.key] = row.stats.window.used_pct

    if not state.seeded:
        # First poll after start: adopt the current position silently, so a
        # restart at 24% does not re-announce 50% and then 25%.
        state.seeded = True
        usage = []

    if state.is_paused(now):
        return []
    # An expired login still surfaces on the first poll: unlike a threshold, it
    # is news every time the app starts, and nothing else will tell the user.
    return info + usage


def _threshold_events(
    row: WindowRow, thresholds: list[int], state: AlertState, provider: str
) -> list[AlertEvent]:
    remaining = row.remaining
    last = state.threshold.get(row.key, THRESHOLD_ARMED)
    if remaining > last:
        # The window refilled; re-arm every level.
        last = THRESHOLD_ARMED
        state.threshold[row.key] = last

    crossed = [t for t in thresholds if remaining <= t < last]
    if not crossed:
        return []

    # Fire the *lowest* level crossed. The reference implementation stepped down
    # one level per tick, so a sharp drop from 100% to 5% announced "50%" first
    # and only reached "10%" four minutes later.
    level = min(crossed)
    state.threshold[row.key] = level
    return [
        AlertEvent(
            kind="threshold",
            key=row.key,
            title=_alert_title(provider),
            body=i18n.t("fmt.notify", label=row.label, pct=remaining),
            tier=row.tier,
            priority=_priority(level),
            row=row,
            provider=provider,
        )
    ]


def _is_active(row: WindowRow, state: AlertState) -> bool:
    """Did this window's usage move since the previous poll?

    A direct measurement beats inferring activity from pace: pace is an average
    over the whole window, so late in one it cannot distinguish someone typing
    right now from someone who stopped an hour ago.
    """
    previous = state.last_used.get(row.key)
    if previous is not None:
        return row.stats.window.used_pct > previous + ACTIVE_DELTA
    return row.stats.pace is not None and row.stats.pace >= ACTIVE_PACE


def _reminder_events(
    row: WindowRow,
    remind_before: list[int],
    state: AlertState,
    clock: datetime,
    active: bool,
    provider: str,
) -> list[AlertEvent]:
    if not remind_before:
        return []
    mins = row.stats.mins_until_reset
    if mins is None or mins <= 0:
        return []

    last = state.remind.get(row.key, REMIND_ARMED)
    if mins > remind_before[0] and last != REMIND_ARMED:
        # A new window started; re-arm and say nothing this tick.
        state.remind[row.key] = REMIND_ARMED
        return []

    crossed = [m for m in remind_before if mins <= m < last]
    if not crossed:
        return []

    level = min(crossed)
    state.remind[row.key] = level
    if active:
        # Consume the level so it cannot fire late, but stay silent: they are
        # already using it and do not need to be told it is coming back.
        return []

    return [
        AlertEvent(
            kind="reminder",
            key=row.key,
            title=_alert_title(provider),
            body=i18n.t(
                "fmt.reset_remind",
                label=row.label,
                mins=mins,
                time=format_local_reset(row.stats.window.resets_at, clock),
            ),
            tier=row.tier,
            row=row,
            provider=provider,
        )
    ]


def _status_events(view: ProviderView, state: AlertState) -> list[AlertEvent]:
    """Announce a problem the user has to act on, once per occurrence."""
    status = view.status
    previous = state.notified_status.get(view.provider)

    if not status.is_actionable:
        if previous is not None:
            state.notified_status.pop(view.provider, None)
        return []
    if previous == status.value:
        return []

    state.notified_status[view.provider] = status.value
    return [
        AlertEvent(
            kind="info",
            key=f"{view.provider}.status",
            title=_alert_title(view.provider),
            body=view.message,
            tier="orange",
            priority="high",
            provider=view.provider,
        )
    ]


def _alert_title(provider: str | None) -> str:
    name = PROVIDER_NAMES.get(provider or "", provider or i18n.t("notify.info_title"))
    return i18n.t("fmt.notify_title", provider=name)


def _priority(level: int) -> Priority:
    if level <= 10:
        return "urgent"
    if level <= 25:
        return "high"
    return "default"


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
