"""Pure derivations over a UsageWindow: remaining, pace, burnout, tier.

No I/O, no Qt, no clock reads except the ``now`` you pass in — which is what
makes the whole alerting layer testable without freezing time globally.
Formulas mirror the upstream monitor so numbers stay comparable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from .models import UsageWindow

WINDOW_5H = 18_000
WINDOW_7D = 604_800

TIER_GREEN = "green"
TIER_ORANGE = "orange"
TIER_RED = "red"

TIER_COLORS = {
    TIER_GREEN: "#2ECC71",
    TIER_ORANGE: "#E67E22",
    TIER_RED: "#E74C3C",
}
TIER_EMOJI = {
    TIER_GREEN: "\U0001F7E2",
    TIER_ORANGE: "\U0001F7E1",
    TIER_RED: "\U0001F534",
}

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

BAR_FILLED = "\u25A0"
BAR_EMPTY = "\u25A1"


def parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 or epoch-seconds reset time into an aware UTC datetime.

    Both APIs are inconsistent here: Anthropic sends ISO strings (sometimes with
    fractional seconds, sometimes ``Z``, sometimes a numeric offset) while the
    Codex endpoint sends epoch integers.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.isdigit():
        return parse_timestamp(int(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def remaining_pct(used_pct: float) -> float:
    """Remaining percentage, one decimal — the inverse of utilization."""
    return round(100.0 - float(used_pct), 1)


def tier_for(remaining: float) -> str:
    """Colour tier. Driven by remaining (not used), truncated like upstream."""
    value = int(remaining)
    if value <= 20:
        return TIER_RED
    if value <= 50:
        return TIER_ORANGE
    return TIER_GREEN


def pace_icon(pace: float | None) -> str:
    if pace is None:
        return ""
    if pace >= 2.0:
        return "\U0001F525"  # fire
    if pace >= 1.3:
        return "\u26A1"      # high voltage
    if pace >= 0.8:
        return "\u2705"      # check
    return "\U0001F422"      # turtle


def format_duration(seconds: float | None) -> str:
    """Coarse human duration: ``2d 3h`` / ``3h 42m`` / ``18m``. Empty when <= 0."""
    if seconds is None:
        return ""
    total = int(seconds)
    if total <= 0:
        return ""
    days, rem = divmod(total, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes = rem // 60
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_local_reset(resets_at: datetime | None, now: datetime | None = None) -> str:
    """Local wall-clock reset time: ``3:49 PM`` today, ``Mar 15 3:49 PM`` otherwise."""
    if resets_at is None:
        return ""
    now = now or datetime.now(timezone.utc)
    if resets_at <= now:
        return ""
    local = resets_at.astimezone()
    hour = local.hour % 12 or 12
    stamp = f"{hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"
    if local.date() == now.astimezone().date():
        return stamp
    return f"{_MONTHS[local.month - 1]} {local.day} {stamp}"


def progress_bar(remaining: float, width: int = 20) -> str:
    filled = max(0, min(width, math.floor(remaining * width / 100)))
    return BAR_FILLED * filled + BAR_EMPTY * (width - filled)


def codex_window_label(window_secs: int | None) -> str:
    """Derive ``5h`` / ``7d`` / ``12h`` from the API-reported window length.

    Upstream hardcoded ``5h``/``7d`` rows and mislabelled weekly-only plans; this
    follows whatever the API actually reports.
    """
    if not window_secs or window_secs <= 0:
        return "limit"
    if window_secs == WINDOW_5H:
        return "5h"
    if window_secs == WINDOW_7D:
        return "7d"
    if window_secs % 86_400 == 0:
        return f"{window_secs // 86_400}d"
    if window_secs % 3_600 == 0:
        return f"{window_secs // 3_600}h"
    return "limit"


@dataclass(frozen=True)
class WindowStats:
    """Everything the UI and alerting need about one window at one instant."""

    window: UsageWindow
    remaining: float
    remaining_int: int
    tier: str
    pace: float | None
    burnout_secs: int | None
    exhausted: bool
    secs_until_reset: int | None

    @property
    def key(self) -> str:
        return self.window.key

    @property
    def color(self) -> str:
        return TIER_COLORS[self.tier]

    @property
    def mins_until_reset(self) -> int | None:
        if self.secs_until_reset is None:
            return None
        return self.secs_until_reset // 60


def derive(window: UsageWindow, now: datetime | None = None) -> WindowStats:
    """Compute pace and burnout for ``window``.

    ``pace`` is usage speed relative to sustainable: 1.0 means you will land
    exactly at 0% when the window resets. It is undefined early in a window
    (nothing elapsed yet) and after the reset time has passed, in which case
    both pace and burnout come back as None rather than a misleading number.
    """
    now = now or datetime.now(timezone.utc)
    used = float(window.used_pct)
    remaining = remaining_pct(used)

    secs_until: int | None = None
    pace: float | None = None
    burnout: int | None = None

    if window.resets_at is not None:
        secs_until = int((window.resets_at - now).total_seconds())
        elapsed = window.window_secs - secs_until
        if secs_until > 0 and elapsed > 0 and int(used) > 0:
            pace = round(used * window.window_secs / (100.0 * elapsed), 1)
            if remaining > 0:
                burnout = int(remaining * elapsed / used)

    return WindowStats(
        window=window,
        remaining=remaining,
        remaining_int=int(remaining),
        tier=tier_for(remaining),
        pace=pace,
        burnout_secs=burnout,
        exhausted=remaining <= 0,
        secs_until_reset=secs_until,
    )
