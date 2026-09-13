"""Provider-agnostic data model.

Providers translate their wire formats into these types, and everything
downstream (compute, alerts, UI) only ever sees these. Adding a third provider
should mean writing one ``providers/*.py`` module and nothing else.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Status(str, Enum):
    """Outcome of a fetch, from the user's point of view rather than HTTP's."""

    OK = "ok"                          # fresh data
    CACHED = "cached"                  # served from cache inside the TTL
    STALE = "stale"                    # request failed, showing older cached data
    NOT_CONFIGURED = "not_configured"  # provider not installed / not logged in
    EXPIRED = "expired"                # credentials present but past expiry
    UNAUTHORIZED = "unauthorized"      # 401 from the API
    UNREADABLE = "unreadable"          # credentials exist but could not be read (keychain refused)
    RATE_LIMITED = "rate_limited"      # 429 and no cache to fall back on
    SCHEMA_CHANGED = "schema_changed"  # HTTP 200 but the fields we need are gone
    ERROR = "error"                    # anything else

    @property
    def has_data(self) -> bool:
        return self in (Status.OK, Status.CACHED, Status.STALE)

    @property
    def is_actionable(self) -> bool:
        """True when the user has to do something (re-login, allow access, report a bug)."""
        return self in (Status.EXPIRED, Status.UNAUTHORIZED, Status.UNREADABLE, Status.SCHEMA_CHANGED)


@dataclass(frozen=True)
class UsageWindow:
    """One rate-limit window.

    ``used_pct`` is utilization (0-100), matching both upstream APIs. Remaining
    is derived, never stored, so the two can never drift apart.
    """

    key: str                       # stable alert key, e.g. "claude.5h"
    used_pct: float
    resets_at: datetime | None
    window_secs: int
    # What this window covers beyond its duration, when it is a sub-limit rather
    # than the account's main quota: "Opus", "Sonnet", "Spark". Providers pass
    # the short distinctive name; the display layer builds the whole label out
    # of this plus window_secs, so the two of them never disagree about wording.
    qualifier: str = ""


@dataclass(frozen=True)
class ExtraUsage:
    """Claude pay-as-you-go balance (the ``spend`` block)."""

    enabled: bool
    used: float | None = None
    limit: float | None = None
    currency: str = "USD"


@dataclass(frozen=True)
class Credits:
    """Codex credit balance."""

    unlimited: bool = False
    balance: float | None = None


@dataclass
class Snapshot:
    """Everything one provider knows at one moment."""

    provider: str
    status: Status
    windows: list[UsageWindow] = field(default_factory=list)
    plan: str | None = None
    extra: ExtraUsage | None = None
    credits: Credits | None = None
    detail: str | None = None          # human-readable source/error note
    fetched_at: float = field(default_factory=time.time)
    window_reset_pending: bool = False  # stale data whose window already rolled over

    @property
    def has_data(self) -> bool:
        return self.status.has_data and bool(self.windows)
