"""Fan an alert out to every enabled channel.

Keeping this in one place means the batching rule — a burst becomes one message,
not five — applies identically to the on-screen toast, the OS notification and
the webhook.
"""

from __future__ import annotations

from typing import Callable

from ..core.alerts import AlertEvent
from ..ui.popup import MAX_VISIBLE, ToastManager
from .formatting import summarize
from .webhook import Webhook


class Dispatcher:
    def __init__(
        self,
        toasts: ToastManager,
        webhook: Webhook,
        *,
        native: Callable[[str, str], None] | None = None,
        native_enabled: bool = True,
    ) -> None:
        self._toasts = toasts
        self._webhook = webhook
        self._native = native
        self._native_enabled = native_enabled

    def set_native_enabled(self, enabled: bool) -> None:
        self._native_enabled = enabled

    def emit(self, events: list[AlertEvent]) -> None:
        if not events:
            return
        self._toasts.show_alerts(events)

        if len(events) > MAX_VISIBLE:
            summary = summarize(events)
            self.notify_native(summary.title, summary.body)
            self._webhook.send_summary(
                summary.title, summary.body, _worst_priority(events), detail=summary.detail
            )
            return

        for event in events:
            self.notify_native(event.title, event.body)
            self._webhook.send(event)

    def notify_native(self, title: str, body: str) -> None:
        if self._native_enabled and self._native is not None:
            self._native(title, body)


def _worst_priority(events: list[AlertEvent]) -> str:
    order = {"default": 0, "high": 1, "urgent": 2}
    return max((e.priority for e in events), key=lambda p: order.get(p, 0))
