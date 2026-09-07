"""Optional outbound webhook, for alerts that should leave the machine.

Two shapes are supported: ntfy (headers carry the title and priority, the body
is the message) and a generic JSON POST for Slack-style incoming webhooks. Both
fire and forget on a worker thread — a slow endpoint must never stall a poll,
and a broken one must never surface as an error dialog.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import httpx

from ..core.alerts import AlertEvent

TIMEOUT = 5.0
log = logging.getLogger("tokentray.webhook")

NTFY_PRIORITY = {"default": "default", "high": "high", "urgent": "urgent"}


class Webhook:
    def __init__(self, *, enabled: bool, kind: str, url: str) -> None:
        self.enabled = bool(enabled and url)
        self.kind = kind
        self.url = url

    @classmethod
    def from_config(cls, config: Any) -> "Webhook":
        return cls(
            enabled=bool(config.get("webhook.enabled", False)),
            kind=str(config.get("webhook.kind", "ntfy")),
            url=str(config.get("webhook.url", "")),
        )

    def send(self, event: AlertEvent) -> None:
        if not self.enabled:
            return
        threading.Thread(
            target=self._post, args=(event,), name="tokentray-webhook", daemon=True
        ).start()

    def send_summary(self, title: str, body: str, priority: str = "default") -> None:
        if not self.enabled:
            return
        event = AlertEvent(kind="info", key="summary", title=title, body=body, priority=priority)
        self.send(event)

    def _post(self, event: AlertEvent) -> None:
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                if self.kind == "ntfy":
                    client.post(
                        self.url,
                        content=event.body.encode("utf-8"),
                        headers={
                            "Title": _ascii(event.title),
                            "Priority": NTFY_PRIORITY.get(event.priority, "default"),
                            "Tags": "warning",
                        },
                    )
                else:
                    client.post(
                        self.url,
                        json={"text": f"{event.title}: {event.body}"},
                        headers={"Content-Type": "application/json"},
                    )
        except Exception as exc:
            # A webhook the user configured badly should show up in the log, not
            # as a popup on top of the alert it was meant to carry.
            log.warning("webhook delivery failed: %s: %s", type(exc).__name__, exc)


def _ascii(text: str) -> str:
    """ntfy sends the title in an HTTP header, which cannot carry raw UTF-8."""
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return json.dumps(text, ensure_ascii=True)[1:-1]
