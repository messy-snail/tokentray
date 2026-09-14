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

from ..core.cache import Cache, CacheEntry
from ..core.config import Config
from ..core.models import Snapshot, Status, UsageWindow
from .diagnostics import log, log_response, log_transport_error
from .retry import MIN_REQUEST_INTERVAL, PROVIDER_LOCKS, rate_limit_delay

HTTP_TIMEOUT = 10.0


class ProviderError(Exception):
    """A fetch attempt failed in a way the user might need to know about."""

    def __init__(
        self, status: Status, detail: str = "", *, retry_after: str | None = None, failure_kind: str = "",
    ) -> None:
        super().__init__(detail or status.value)
        self.status = status
        self.detail = detail
        self.retry_after = retry_after
        self.failure_kind = failure_kind or status.value


class SchemaError(ProviderError):
    """HTTP 200, but the fields we depend on are missing.

    Both usage endpoints are undocumented, so this is the expected failure mode
    when a provider reshapes their response. It is reported as its own status so
    the UI can say "the API changed" instead of a generic error.
    """

    def __init__(self, detail: str = "") -> None:
        super().__init__(Status.SCHEMA_CHANGED, detail)


class CredentialsUnreadable(Exception):
    """Credentials exist, but reading them was refused or went unanswered.

    Not the same as "not configured": signing in again does not help, and
    retrying without the user can mean an authorization prompt every time.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class BaseProvider:
    id: str = "base"

    def __init__(self, config: Config, cache: Cache | None = None, client: httpx.Client | None = None) -> None:
        self.config = config
        self.cache = cache or Cache()
        self._client = client
        self._owns_client = client is None

    # -- subclass hooks --------------------------------------------------------

    def credentials(self, *, interactive: bool = False) -> Any | None:
        """Return whatever ``fetch_live`` needs, or None when not set up.

        ``interactive`` is True only when the user asked for this read (a forced
        refresh, "Check again"). A source that refused an earlier automatic read
        is retried only then; raise CredentialsUnreadable for such a refusal.
        """
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
            self._client = httpx.Client(
                timeout=HTTP_TIMEOUT, follow_redirects=False,
                event_hooks={"response": [lambda response: log_response(self.id, response)]},
            )
        return self._client

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            self._client.close()
            self._client = None

    def fetch(self, *, force: bool = False, now: float | None = None) -> Snapshot:
        with PROVIDER_LOCKS.get(self.id, PROVIDER_LOCKS["base"]):
            return self._fetch(force=force, now=now)

    def _fetch(self, *, force: bool, now: float | None) -> Snapshot:
        now = time.time() if now is None else now
        ttl = self.config.cache_ttl
        entry = self.cache.load(self.id)

        # Hard request gates also apply to forced refreshes and fresh caches.
        if entry is not None:
            if entry.rate_limit_until > now:
                snapshot = self._cached_failure(entry, Status.RATE_LIMITED)
                snapshot.failure_kind = "rate_limited"
                snapshot.retry_at = entry.rate_limit_until
                snapshot.request_skipped = True
                return snapshot
            if entry.last_attempt > 0 and now < entry.last_attempt + MIN_REQUEST_INTERVAL:
                snapshot = self._cached_failure(entry, Status.ERROR) if entry.failure_kind else (
                    self._decorate(entry.body, Status.CACHED, "recent data", fetched_at=entry.fetched_at)
                    if entry.body else Snapshot(provider=self.id, status=Status.ERROR)
                )
                snapshot.retry_at = entry.last_attempt + MIN_REQUEST_INTERVAL
                snapshot.request_skipped = True
                return snapshot

        if not force and entry is not None and entry.body:
            if entry.is_fresh(ttl, now):
                return self._decorate(
                    entry.body, Status.CACHED, f"cached ({int(entry.age(now))}s ago)",
                    fetched_at=entry.fetched_at,
                )
            if entry.in_backoff(now):
                return self._cached_failure(entry, Status.ERROR)
        elif not force and entry is not None and entry.in_backoff(now):
            return self._cached_failure(entry, Status.ERROR)

        try:
            creds = self.credentials(interactive=force)
        except CredentialsUnreadable as exc:
            # Like expiry, this is the user's to fix: no request, no backoff, and
            # no cached numbers dressed up as merely stale.
            return Snapshot(provider=self.id, status=Status.UNREADABLE, detail=exc.detail)
        if creds is None:
            return Snapshot(provider=self.id, status=Status.NOT_CONFIGURED)

        blocked = self.precheck(creds)
        if blocked is not None:
            return Snapshot(provider=self.id, status=blocked)

        self.cache.mark_attempt(self.id, now)
        try:
            body = self.fetch_live(creds)
        except ProviderError as exc:
            log.warning(
                "provider=%s fetch_failed status=%s exception=%s", self.id, exc.status.value, type(exc).__name__,
            )
            return self._on_failure(exc, ttl, now)
        except httpx.HTTPError as exc:
            log_transport_error(self.id, exc)
            return self._on_failure(
                ProviderError(Status.ERROR, type(exc).__name__, failure_kind="connection"), ttl, now,
            )

        try:
            snapshot = self.parse(body)
        except SchemaError as exc:
            log.warning("provider=%s schema_changed", self.id)
            # Do not cache a body we cannot read, but do back off: hammering the
            # endpoint will not make it go back to the old shape.
            return self._on_failure(exc, ttl, now)

        self.cache.store(self.id, body, now)
        snapshot.status = Status.OK
        snapshot.detail = "live"
        snapshot.fetched_at = now
        return snapshot

    # -- helpers ---------------------------------------------------------------

    def _on_failure(self, exc: ProviderError, ttl: float, now: float) -> Snapshot:
        retry_at = 0.0
        if exc.status is Status.RATE_LIMITED:
            previous = self.cache.load(self.id)
            delay, reason = rate_limit_delay(
                exc.retry_after, now, self.config.poll_interval, previous.rate_limit_count if previous else 0,
            )
            retry_at = now + delay
            log.warning("provider=%s http_status=429 retry_in_seconds=%s reason=%s", self.id, delay, reason)
        kept = self.cache.mark_failure(
            self.id, ttl, exc.detail or exc.status.value, now,
            failure_kind=exc.failure_kind, rate_limit_until=retry_at,
        )
        if kept is not None and kept.body and not exc.status.is_actionable:
            snapshot = self._decorate(
                kept.body, Status.STALE, exc.detail or exc.status.value, fetched_at=kept.fetched_at,
            )
        else:
            snapshot = Snapshot(provider=self.id, status=exc.status, detail=exc.detail, fetched_at=0.0)
        snapshot.failure_kind = exc.failure_kind
        snapshot.retry_at = retry_at
        return snapshot

    def _cached_failure(self, entry: CacheEntry, status: Status) -> Snapshot:
        try:
            failure_status = Status(entry.failure_kind)
        except ValueError:
            failure_status = status
        if failure_status.is_actionable:
            return Snapshot(
                provider=self.id, status=failure_status, detail=entry.note,
                failure_kind=entry.failure_kind, request_skipped=True, fetched_at=0.0,
            )
        snapshot = (
            self._decorate(entry.body, Status.STALE, entry.note, fetched_at=entry.fetched_at)
            if entry.body else Snapshot(provider=self.id, status=status, detail=entry.note, fetched_at=0.0)
        )
        snapshot.failure_kind = entry.failure_kind
        snapshot.request_skipped = True
        return snapshot

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
