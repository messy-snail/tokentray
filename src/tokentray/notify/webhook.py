"""Optional queued delivery to ntfy, generic, Slack, or Discord webhooks."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from ..core.alerts import AlertEvent
from ..core.compute import TIER_COLORS
from ..core.i18n import t
from ..core.secrets import WEBHOOK_URL, SecretStore, default_store
from .formatting import provider_name

TIMEOUT = 5.0
MAX_RETRY_AFTER = 30.0
SUPPORTED_KINDS = ("ntfy", "generic", "slack", "discord")
log = logging.getLogger("tokentray.webhook")

NTFY_PRIORITY = {"default": "default", "high": "high", "urgent": "urgent"}


@dataclass(frozen=True)
class DeliveryResult:
    ok: bool
    status_code: int | None = None
    error: str = ""


class Webhook:
    """Serialize outbound messages so alerts cannot create a thread burst."""

    def __init__(
        self,
        *,
        enabled: bool,
        kind: str,
        url: str = "",
        store: SecretStore | None = None,
        configured: bool | None = None,
    ) -> None:
        self.enabled = bool(enabled and (configured if configured is not None else url))
        self.kind = kind if kind in SUPPORTED_KINDS else "generic"
        self.url = url
        self._store = store
        self._generation = 0
        self._queue: queue.Queue[
            tuple[int, AlertEvent, Callable[[DeliveryResult], None] | None]
        ] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, config: Any, store: SecretStore | None = None) -> "Webhook":
        legacy_url = str(config.get("webhook.url", ""))
        configured = bool(config.get("webhook.configured", False) or legacy_url)
        return cls(
            enabled=bool(config.get("webhook.enabled", False)),
            kind=str(config.get("webhook.kind", "ntfy")),
            url=legacy_url,
            store=store or default_store(),
            configured=configured,
        )

    def reconfigure(
        self, *, enabled: bool, kind: str, url: str = "", configured: bool = False
    ) -> None:
        """Apply saved settings and invalidate messages queued for the old target."""
        with self._lock:
            self._generation += 1
            self.enabled = bool(enabled and (configured or url))
            self.kind = kind if kind in SUPPORTED_KINDS else "generic"
            self.url = url

    def reconfigure_from_config(self, config: Any) -> None:
        legacy_url = str(config.get("webhook.url", ""))
        self.reconfigure(
            enabled=bool(config.get("webhook.enabled", False)),
            kind=str(config.get("webhook.kind", "ntfy")),
            url=legacy_url,
            configured=bool(config.get("webhook.configured", False) or legacy_url),
        )

    def send(self, event: AlertEvent) -> None:
        if self.enabled:
            self._enqueue(event, None)

    def send_summary(
        self,
        title: str,
        body: str,
        priority: str = "default",
        *,
        detail: str = "",
    ) -> None:
        self.send(
            AlertEvent(
                kind="info",
                key="summary",
                title=title,
                body=body,
                priority=priority,
                detail=detail,
            )
        )

    def test(self, callback: Callable[[DeliveryResult], None]) -> None:
        event = AlertEvent(
            kind="info",
            key="test",
            title="tokentray",
            body="Webhook notifications are working.",
            tier="green",
        )
        self._enqueue(event, callback)

    def deliver(self, event: AlertEvent) -> DeliveryResult:
        """Deliver one event synchronously; used by the queue and CLI tests."""
        kind, url = self._destination()
        error = validate_destination(kind, url)
        if error:
            return DeliveryResult(False, error=error)
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                response = self._request(client, kind, url, event)
                if response.status_code == 429:
                    time.sleep(_retry_after(response))
                    response = self._request(client, kind, url, event)
                response.raise_for_status()
                if kind == "slack" and response.text.strip().lower() not in ("", "ok"):
                    return DeliveryResult(False, response.status_code, "unexpected response")
                return DeliveryResult(True, response.status_code)
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            log.warning("webhook delivery failed: HTTP %s", code)
            return DeliveryResult(False, code, f"HTTP {code}")
        except Exception as exc:
            name = type(exc).__name__
            log.warning("webhook delivery failed: %s", name)
            return DeliveryResult(False, error=name)

    def close(self) -> None:
        with self._lock:
            self._generation += 1
            self.enabled = False

    def _enqueue(
        self, event: AlertEvent, callback: Callable[[DeliveryResult], None] | None
    ) -> None:
        with self._lock:
            generation = self._generation
            self._queue.put((generation, event, callback))
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._work, name="tokentray-webhook", daemon=True
                )
                self._worker.start()

    def _work(self) -> None:
        while True:
            try:
                generation, event, callback = self._queue.get(timeout=1.0)
            except queue.Empty:
                with self._lock:
                    if self._queue.empty():
                        self._worker = None
                        return
                continue
            try:
                with self._lock:
                    current = self._generation
                if generation != current:
                    continue
                result = self.deliver(event)
                if callback is not None:
                    try:
                        callback(result)
                    except Exception:
                        log.exception("webhook result callback failed")
            finally:
                self._queue.task_done()

    def _destination(self) -> tuple[str, str]:
        with self._lock:
            kind, url = self.kind, self.url
        if not url and self._store is not None:
            url = self._store.get(WEBHOOK_URL) or ""
        return kind, url

    def _request(
        self, client: httpx.Client, kind: str, url: str, event: AlertEvent
    ) -> httpx.Response:
        if kind == "ntfy":
            return client.post(
                url,
                content=_message(event).encode("utf-8"),
                headers={
                    "Title": _ascii(event.title),
                    "Priority": NTFY_PRIORITY.get(event.priority, "default"),
                    "Tags": "warning",
                },
            )
        if kind == "slack":
            return client.post(url, json=_slack_payload(event))
        if kind == "discord":
            return client.post(url, params={"wait": "true"}, json=_discord_payload(event))
        return client.post(url, json={"text": f"{event.title}: {_message(event)}"})


def validate_destination(kind: str, url: str) -> str:
    if kind not in SUPPORTED_KINDS:
        return "unsupported webhook service"
    parsed = urlparse(url.strip())
    allowed_schemes = {"https"} if kind in {"slack", "discord"} else {"http", "https"}
    if parsed.scheme not in allowed_schemes or not parsed.netloc:
        return "a valid webhook URL is required"
    host = parsed.hostname or ""
    if kind == "slack":
        valid_host = host in {"hooks.slack.com", "hooks.slack-gov.com"}
        if not valid_host or not parsed.path.startswith("/services/"):
            return "this is not a Slack incoming webhook URL"
    if kind == "discord":
        valid_host = host in {"discord.com", "www.discord.com", "discordapp.com"}
        if not valid_host or "/api/webhooks/" not in parsed.path:
            return "this is not a Discord webhook URL"
    return ""


# Deliberately next to validate_destination: this is the same knowledge phrased
# for a person, and the two drifting apart would mean telling someone to paste a
# URL the validator then rejects.
DESTINATION_HINTS = {
    "slack": "https://hooks.slack.com/services/T…/B…/…",
    "discord": "https://discord.com/api/webhooks/<id>/<token>",
    "ntfy": "https://ntfy.sh/<topic>",
}


def destination_hint(kind: str) -> str:
    """The URL shape ``validate_destination`` will accept for ``kind``.

    Empty for a generic webhook, which is any HTTPS endpoint taking a JSON POST
    and so has no shape to show.
    """
    return DESTINATION_HINTS.get(kind, "")


def _message(event: AlertEvent) -> str:
    detail = event.detail
    if not detail and event.row is not None:
        detail = " · ".join(part for part in (event.row.refills, event.row.pace) if part)
    return f"{event.body}\n{detail}" if detail else event.body


def _slack_payload(event: AlertEvent) -> dict[str, Any]:
    message = _message(event)
    return {
        "text": f"{event.title}: {message}",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": event.title[:150]}},
            {"type": "section", "text": {"type": "mrkdwn", "text": message[:3000]}},
        ],
    }


def _discord_payload(event: AlertEvent) -> dict[str, Any]:
    color = int(TIER_COLORS.get(event.tier, TIER_COLORS["green"]).lstrip("#"), 16)
    title = event.title
    description = _message(event)[:4096]
    embed: dict[str, Any] = {"color": color}
    if event.provider:
        embed["author"] = {"name": provider_name(event.provider)[:256]}
        if event.kind == "info" and title == t("fmt.notify_title", provider=provider_name(event.provider)):
            title = t("discord.status_title")
    if event.key == "test.usage":
        title = t("discord.usage_title")
    elif event.kind in {"threshold", "reminder"}:
        title = t(f"discord.{event.kind}_title")
    if event.row is not None:
        row = event.row
        remaining = row.detail_status or row.remaining_text
        marker = "ℹ️" if row.detail_status else {"green": "🟢", "orange": "🟠", "red": "🔴"}.get(row.tier, "ℹ️")
        description = f"{row.label[:256]}\n**{marker} {remaining[:256]}**"
        if event.detail:
            description += f"\n\n{event.detail[:1024]}"
        fields = []
        # The view already includes the local reset time; keep it without
        # repeating the label in both the field name and its value.
        refills = next((item.value for item in row.details if item.key == "refills"), "")
        refills = refills or row.refills.removeprefix(t("label.refills") + " ")
        pace = row.pace.removeprefix(t("label.pace") + ": ")
        for key, value in (("refills", refills), ("pace", pace)):
            if value.strip():
                icon = "🕒" if key == "refills" else "⚡"
                fields.append({"name": f"{icon} {t(f'label.{key}')}", "value": value[:1024], "inline": True})
        if fields:
            embed["fields"] = fields
    elif event.key == "test" and event.body == "Webhook notifications are working.":
        title = t("discord.test_title")
        description = t("discord.test_body")
    embed.update(title=title[:256], description=description)
    if event.row is not None:
        summary = f"{marker} {provider_name(event.provider)} · {row.label} · {remaining}"
        if event.kind == "reminder":
            summary = f"{title} · {provider_name(event.provider)} · {row.label} · {row.refills or remaining}"
        if event.detail:
            summary += f" · {event.detail}"
    else:
        summary = " · ".join(part for part in (title, provider_name(event.provider) if event.provider else "",
                                               description) if part)
    summary = " ".join(summary.split())
    return {
        "username": "tokentray",
        "content": summary if len(summary) <= 240 else summary[:239] + "…",
        "allowed_mentions": {"parse": []},
        "embeds": [embed],
    }


def _retry_after(response: httpx.Response) -> float:
    raw: Any = response.headers.get("Retry-After")
    if raw is None:
        try:
            raw = response.json().get("retry_after", 0)
        except (ValueError, AttributeError):
            raw = 0
    try:
        return max(0.0, min(float(raw), MAX_RETRY_AFTER))
    except (TypeError, ValueError):
        return 0.0


def _ascii(text: str) -> str:
    """ntfy sends the title in an HTTP header, which cannot carry raw UTF-8."""
    try:
        text.encode("ascii")
        return text
    except UnicodeEncodeError:
        return json.dumps(text, ensure_ascii=True)[1:-1]
