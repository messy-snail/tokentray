"""Route local alerts and independently deliver enabled webhook notifications.

Windows prefers native banners, retaining custom cards for recovery actions and
submission failures. Other platforms use custom cards plus native delivery.
"""

from __future__ import annotations

import logging
import sys
from typing import Callable

from ..core.alerts import AlertEvent
from ..ui.popup import MAX_VISIBLE, ToastManager
from .formatting import summarize
from .webhook import Webhook

log = logging.getLogger("tokentray.notify")


class Dispatcher:
    def __init__(
        self,
        toasts: ToastManager,
        webhook: Webhook,
        *,
        native: Callable[[str, str], bool] | None = None,
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
        self._emit_local(events)

        if len(events) > MAX_VISIBLE:
            summary = summarize(events)
            self._webhook.send_summary(
                summary.title, summary.body, _worst_priority(events), detail=summary.detail
            )
            return

        for event in events:
            self._webhook.send(event)

    def present(
        self, title: str, body: str, show_custom: Callable[[], None],
        *, force_custom: bool = False,
    ) -> None:
        """Choose a local channel without duplicating Windows banners."""
        if sys.platform == "win32":
            if force_custom or not self.notify_native(title, body):
                show_custom()
        else:
            show_custom()
            self.notify_native(title, body)

    def _emit_local(self, events: list[AlertEvent]) -> None:
        if sys.platform != "win32" or any(e.login_required for e in events):
            self._toasts.show_alerts(events)
            if sys.platform == "win32":
                return
            if len(events) > MAX_VISIBLE:
                summary = summarize(events)
                self.notify_native(summary.title, summary.body)
            else:
                for event in events:
                    self.notify_native(event.title, event.body)
            return

        if len(events) > MAX_VISIBLE:
            summary = summarize(events)
            self.present(summary.title, summary.body, lambda: self._toasts.show_alerts(events))
        else:
            for event in events:
                self.present(
                    event.title, event.body,
                    lambda event=event: self._toasts.show_alerts([event]),
                )

    def notify_native(self, title: str, body: str) -> bool:
        """Return whether submission succeeded, not whether a banner appeared."""
        if self._native_enabled and self._native is not None:
            try:
                return self._native(title, body)
            except Exception:
                log.warning("native notification failed: %s", title, exc_info=True)
        return False


def _worst_priority(events: list[AlertEvent]) -> str:
    order = {"default": 0, "high": 1, "urgent": 2}
    return max((e.priority for e in events), key=lambda p: order.get(p, 0))
