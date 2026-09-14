"""Structured per-provider refresh outcomes shared by the worker and UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .i18n import t
from .models import Snapshot, Status


@dataclass(frozen=True)
class ProviderRefresh:
    provider: str
    outcome: str
    failure_kind: str = ""
    retry_at: float = 0.0


@dataclass(frozen=True)
class RefreshResult:
    providers: tuple[ProviderRefresh, ...]

    @classmethod
    def from_snapshots(cls, snapshots: list[Snapshot]) -> RefreshResult:
        entries = []
        for snapshot in snapshots:
            if snapshot.status is Status.NOT_CONFIGURED:
                continue
            kind = snapshot.failure_kind
            if not kind and snapshot.status not in (Status.OK, Status.CACHED):
                kind = snapshot.status.value
            outcome = "failed" if kind else "done" if snapshot.status is Status.OK else "retained"
            if kind == "rate_limited" and snapshot.request_skipped:
                outcome = "waiting"
            entries.append(ProviderRefresh(snapshot.provider, outcome, kind, snapshot.retry_at))
        return cls(tuple(entries))

    @property
    def successful(self) -> bool:
        return bool(self.providers) and all(p.outcome == "done" for p in self.providers)

    @property
    def text(self) -> str:
        if not self.providers:
            return t("refresh.no_providers")
        lines = []
        for item in self.providers:
            provider = {"claude": "Claude", "codex": "Codex"}.get(item.provider, item.provider)
            lines.append(t(
                "refresh.provider_" + item.outcome,
                provider=provider, reason=failure_text(item.failure_kind),
            ))
        return "\n".join(lines)


def failure_text(kind: str) -> str:
    key = {
        "rate_limited": "limited", "connection": "connection", "expired": "expired",
        "unauthorized": "expired", "unreadable": "unreadable", "schema_changed": "schema",
    }.get(kind, "error")
    return t("refresh.reason_" + key)


def local_timestamp(timestamp: float) -> str:
    try:
        value = datetime.fromtimestamp(timestamp).astimezone()
    except (ValueError, OverflowError, OSError):
        return "?"
    return t("refresh.timestamp", month=value.month, day=value.day, hour=value.hour, minute=value.minute)
