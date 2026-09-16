"""Shared manual usage fetching and webhook delivery for the CLI and GUI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from ..core.cache import Cache
from ..core.config import Config
from ..core.view import ProviderView, build_view
from .formatting import usage_preview_events
from .webhook import Webhook


@dataclass(frozen=True)
class PreviewResult:
    sent: int = 0
    error: str = ""
    empty: bool = False


def collect_views(config: Config, *, force: bool) -> list[ProviderView]:
    """Fetch enabled providers and close every client, including on failure."""
    from ..providers import build_providers

    providers = build_providers(config, Cache())
    try:
        return [build_view(provider.fetch(force=force), datetime.now(timezone.utc)) for provider in providers]
    finally:
        for provider in providers:
            provider.close()


def send_usage_preview(
    config: Config, hook: Webhook, *, progress: Callable[[str], None] | None = None,
) -> PreviewResult:
    """Send quota cards in order, stopping at the first failure without touching alert state."""
    sent = 0
    try:
        if progress:
            progress("fetching")
        events = usage_preview_events(collect_views(config, force=True))
        if not events:
            return PreviewResult(empty=True)
        if progress:
            progress("sending")
        for event in events:
            result = hook.deliver(event)
            if not result.ok:
                return PreviewResult(sent=sent, error=result.error or "unknown error")
            sent += 1
        return PreviewResult(sent=sent)
    except Exception as exc:
        # Provider/transport exceptions may contain credentials or private URLs.
        return PreviewResult(sent=sent, error=type(exc).__name__)
