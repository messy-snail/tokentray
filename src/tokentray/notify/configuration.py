"""Persistence rules for the single selected outbound notification target."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.config import Config
from ..core.secrets import WEBHOOK_URL, SecretStore, default_store
from .webhook import SUPPORTED_KINDS, validate_destination


@dataclass(frozen=True)
class DestinationSettings:
    enabled: bool
    kind: str
    configured: bool
    url: str = ""


def current_settings(config: Config) -> DestinationSettings:
    legacy_url = str(config.get("webhook.url", ""))
    kind = str(config.get("webhook.kind", "ntfy"))
    if kind not in SUPPORTED_KINDS:
        kind = "generic"
    return DestinationSettings(
        enabled=bool(config.get("webhook.enabled", False)),
        kind=kind,
        configured=bool(config.get("webhook.configured", False) or legacy_url),
        url=legacy_url,
    )


def save_destination(
    config: Config,
    *,
    enabled: bool,
    kind: str,
    url: str = "",
    store: SecretStore | None = None,
) -> DestinationSettings:
    """Validate and atomically move webhook URLs out of the regular config."""
    if kind not in SUPPORTED_KINDS:
        raise ValueError("unsupported webhook service")

    store = store or default_store()
    previous = current_settings(config)
    if url.strip():
        error = validate_destination(kind, url.strip())
        if error:
            raise ValueError(error)
    old_secret = store.get(WEBHOOK_URL)
    url = url.strip()
    configured = previous.kind == kind and bool(previous.url or old_secret)

    pending_secret = old_secret
    if url:
        pending_secret = url
        configured = True
    elif previous.url and previous.kind == kind:
        # One-way migration for versions that kept the URL in plain TOML.
        pending_secret = previous.url
        configured = True
    elif previous.kind != kind:
        pending_secret = None
        configured = False

    if enabled and not configured:
        raise ValueError("enter a webhook URL before enabling notifications")

    old_values = {
        "webhook.enabled": config.get("webhook.enabled", False),
        "webhook.kind": config.get("webhook.kind", "ntfy"),
        "webhook.configured": config.get("webhook.configured", False),
        "webhook.url": config.get("webhook.url", ""),
    }
    try:
        if pending_secret:
            store.set(WEBHOOK_URL, pending_secret)
        else:
            store.delete(WEBHOOK_URL)
        config.set("webhook.enabled", enabled)
        config.set("webhook.kind", kind)
        config.set("webhook.configured", configured)
        config.set("webhook.url", "")
        config.save()
    except Exception:
        if old_secret:
            store.set(WEBHOOK_URL, old_secret)
        else:
            store.delete(WEBHOOK_URL)
        for key, value in old_values.items():
            config.set(key, value)
        raise
    return DestinationSettings(enabled, kind, configured, url)
