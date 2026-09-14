"""Provider request pacing independent of successful-response cache freshness."""

from __future__ import annotations

import math
import threading
from email.utils import parsedate_to_datetime

MIN_REQUEST_INTERVAL = 30
PROVIDER_LOCKS = {key: threading.RLock() for key in ("claude", "codex", "base")}


def retry_delay(header: str | None, now: float) -> float | None:
    if not header:
        return None
    value = header.strip()
    try:
        if value.isascii() and value.isdecimal():
            delay = float(value)
        else:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            delay = date.timestamp() - now
    except (ValueError, TypeError, OverflowError):
        return None
    return delay if math.isfinite(delay) and 0 < delay and now + delay < 253402214400 else None


def rate_limit_delay(header: str | None, now: float, interval: int, previous_count: int) -> tuple[float, str]:
    server = retry_delay(header, now)
    if server is not None:
        return max(interval, server), "retry_after"
    fallback = min(300 * 2 ** min(max(previous_count, 0), 4), 3600)
    return max(interval, fallback), "exponential_backoff"
