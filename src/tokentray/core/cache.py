"""Response cache with explicit freshness and backoff timestamps.

Upstream encoded backoff by touching the cache file's mtime on failure, which
works but means "when did we last succeed" and "when may we retry" are the same
number — you cannot tell a fresh success from a suppressed failure. Storing both
as fields keeps the two questions separate and makes the tests readable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import paths


@dataclass
class CacheEntry:
    body: dict[str, Any]
    fetched_at: float       # when the body was last successfully retrieved
    backoff_until: float    # do not hit the network again before this
    note: str = ""          # why the last attempt failed, if it did

    def age(self, now: float | None = None) -> float:
        return max(0.0, (now if now is not None else time.time()) - self.fetched_at)

    def is_fresh(self, ttl: float, now: float | None = None) -> bool:
        return self.age(now) < ttl

    def in_backoff(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) < self.backoff_until


class Cache:
    """One JSON file per provider under the platform cache directory."""

    def __init__(self, directory: Path | None = None) -> None:
        self._dir = directory

    def _path(self, provider_id: str) -> Path:
        if self._dir is not None:
            self._dir.mkdir(parents=True, exist_ok=True)
            return self._dir / f"{provider_id}.json"
        return paths.cache_file(provider_id)

    def load(self, provider_id: str) -> CacheEntry | None:
        raw = paths.read_json(self._path(provider_id))
        if not raw or not isinstance(raw.get("body"), dict):
            return None
        return CacheEntry(
            body=raw["body"],
            fetched_at=_as_float(raw.get("fetched_at")),
            backoff_until=_as_float(raw.get("backoff_until")),
            note=str(raw.get("note") or ""),
        )

    def store(self, provider_id: str, body: dict[str, Any], now: float | None = None) -> CacheEntry:
        entry = CacheEntry(
            body=body,
            fetched_at=now if now is not None else time.time(),
            backoff_until=0.0,
            note="",
        )
        self._write(provider_id, entry)
        return entry

    def mark_failure(
        self,
        provider_id: str,
        ttl: float,
        note: str,
        now: float | None = None,
    ) -> CacheEntry | None:
        """Record a failed attempt and hold off retrying for ``ttl`` seconds.

        The cached body (if any) is preserved so the UI can keep showing stale
        numbers instead of blanking out.
        """
        now = now if now is not None else time.time()
        entry = self.load(provider_id)
        if entry is None:
            entry = CacheEntry(body={}, fetched_at=0.0, backoff_until=now + ttl, note=note)
        else:
            entry.backoff_until = now + ttl
            entry.note = note
        self._write(provider_id, entry)
        return entry if entry.body else None

    def clear(self, provider_id: str) -> None:
        self._path(provider_id).unlink(missing_ok=True)

    def _write(self, provider_id: str, entry: CacheEntry) -> None:
        paths.atomic_write_json(
            self._path(provider_id),
            {
                "body": entry.body,
                "fetched_at": entry.fetched_at,
                "backoff_until": entry.backoff_until,
                "note": entry.note,
            },
            private=True,
        )


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
