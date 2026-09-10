"""Shared provider machinery: caching, backoff, and status mapping.

Subclasses supply three things — how to find credentials, how to make the HTTP
call, and how to turn the response body into windows. Everything about when to
call, when to keep quiet, and what to show when a call fails lives here so both
providers behave identically under failure.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from ..core.cache import Cache
from ..core.config import Config
from ..core.models import Snapshot, Status, UsageWindow

HTTP_TIMEOUT = 10.0


class ProviderError(Exception):
    """A fetch attempt failed in a way the user might need to know about."""

    def __init__(self, status: Status, detail: str = "") -> None:
        super().__init__(detail or status.value)
        self.status = status
        self.detail = detail


class SchemaError(ProviderError):
    """HTTP 200, but the fields we depend on are missing.

    Both usage endpoints are undocumented, so this is the expected failure mode
    when a provider reshapes their response. It is reported as its own status so
    the UI can say "the API changed" instead of a generic error.
    """

    def __init__(self, detail: str = "") -> None:
        super().__init__(Status.SCHEMA_CHANGED, detail)


class BaseProvider:
    id: str = "base"

    def __init__(self, config: Config, cache: Cache | None = None, client: httpx.Client | None = None) -> None:
        self.config = config
        self.cache = cache or Cache()
        self._client = client
        self._owns_client = client is None

    # -- subclass hooks --------------------------------------------------------

    def credentials(self) -> Any | None:
        """Return whatever ``fetch_live`` needs, or None when not set up."""
        raise NotImplementedError

    def fetch_live(self, creds: Any) -> dict[str, Any]:
        """Perform the request. Raise ProviderError on any non-success."""
        raise NotImplementedError

    def parse(self, body: dict[str, Any]) -> Snapshot:
        """Turn a response body into a Snapshot. Raise SchemaError if unusable."""
        raise NotImplementedError

    def precheck(self, creds: Any) -> Status | None:
        """Optional cheap check before spending a request (e.g. token expiry)."""
        return None

    # -- driver ----------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return bool(self.config.get(f"{self.id}.enabled", True))

    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=False)
        return self._client

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            self._client.close()
            self._client = None

    def fetch(self, *, force: bool = False, now: float | None = None) -> Snapshot:
        now = time.time() if now is None else now
        ttl = self.config.cache_ttl
        entry = self.cache.load(self.id)

        if not force and entry is not None and entry.body:
            if entry.is_fresh(ttl, now):
                return self._decorate(entry.body, Status.CACHED, f"cached ({int(entry.age(now))}s ago)", fetched_at=entry.fetched_at)
            if entry.in_backoff(now):
                return self._decorate(entry.body, Status.STALE, entry.note or "stale", fetched_at=entry.fetched_at)
        elif not force and entry is not None and entry.in_backoff(now):
            return Snapshot(provider=self.id, status=Status.ERROR, detail=entry.note or "error")

        creds = self.credentials()
        if creds is None:
            return Snapshot(provider=self.id, status=Status.NOT_CONFIGURED)

        blocked = self.precheck(creds)
        if blocked is not None:
            return Snapshot(provider=self.id, status=blocked)

        try:
            body = self.fetch_live(creds)
        except ProviderError as exc:
            return self._on_failure(exc, ttl, now)
        except httpx.HTTPError as exc:
            return self._on_failure(ProviderError(Status.ERROR, type(exc).__name__), ttl, now)

        try:
            snapshot = self.parse(body)
        except SchemaError as exc:
            # Do not cache a body we cannot read, but do back off: hammering the
            # endpoint will not make it go back to the old shape.
            self.cache.mark_failure(self.id, ttl, exc.detail or "schema changed", now)
            return Snapshot(provider=self.id, status=Status.SCHEMA_CHANGED, detail=exc.detail)

        self.cache.store(self.id, body, now)
        snapshot.status = Status.OK
        snapshot.detail = "live"
        snapshot.fetched_at = now
        return snapshot

    # -- helpers ---------------------------------------------------------------

    def _on_failure(self, exc: ProviderError, ttl: float, now: float) -> Snapshot:
        kept = self.cache.mark_failure(self.id, ttl, exc.detail or exc.status.value, now)
        if kept is not None and kept.body and not exc.status.is_actionable:
            return self._decorate(kept.body, Status.STALE, exc.detail or exc.status.value, fetched_at=kept.fetched_at)
        return Snapshot(provider=self.id, status=exc.status, detail=exc.detail)

    def _decorate(
        self, body: dict[str, Any], status: Status, detail: str, *, fetched_at: float,
    ) -> Snapshot:
        try:
            snapshot = self.parse(body)
        except SchemaError as exc:
            return Snapshot(provider=self.id, status=Status.SCHEMA_CHANGED, detail=exc.detail)
        snapshot.status = status
        snapshot.detail = detail
        snapshot.fetched_at = fetched_at
        if status is Status.STALE:
            snapshot.window_reset_pending = _any_window_elapsed(snapshot.windows)
        return snapshot


def _any_window_elapsed(windows: list[UsageWindow]) -> bool:
    """True when cached data describes a window that has since reset.

    Once that happens the cached percentage is meaningless — the window refilled
    while we were rate-limited — so the UI shows ``~0%`` rather than a stale number.
    """
    import datetime as _dt

    now = _dt.datetime.now(_dt.timezone.utc)
    return any(w.resets_at is not None and w.resets_at <= now for w in windows)
