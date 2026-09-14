"""Allowlisted network diagnostics: never serialize requests or exception text."""

from __future__ import annotations

import logging
import socket
import ssl

import httpx

log = logging.getLogger("tokentray.network")


def log_transport_error(provider: str, error: Exception) -> None:
    chain: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        # Messages may contain credentials, URLs, or local paths. Inspect them
        # only to select fixed labels; never send the original text to logging.
        message = str(current).lower()
        reason = "unknown"
        if isinstance(current, ssl.SSLCertVerificationError) or "certificate_verify_failed" in message:
            reason = "certificate_verification_failed"
        elif "revocation" in message or "0x80092012" in message:
            reason = "certificate_revocation_check_failed"
        elif isinstance(current, socket.gaierror) or "getaddrinfo failed" in message:
            reason = "dns_lookup_failed"
        elif isinstance(current, ConnectionRefusedError):
            reason = "connection_refused"
        elif isinstance(current, (TimeoutError, httpx.TimeoutException)):
            reason = "timeout"
        elif isinstance(current, ssl.SSLError):
            reason = "tls_error"
        elif isinstance(current, httpx.ProxyError):
            reason = "proxy_error"
        fields = [type(current).__name__, f"reason={reason}"]
        for key in ("errno", "winerror", "verify_code"):
            value = getattr(current, key, None)
            if type(value) is int:
                fields.append(f"{key}={value}")
        chain.append("(" + " ".join(fields) + ")")
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    log.warning("provider=%s transport_failed chain=%s", provider, " <- ".join(chain))


def log_response(provider: str, response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    # Only accept bounded ASCII seconds, never arbitrary header contents.
    retry = response.headers.get("retry-after", "")
    seconds = retry if retry.isascii() and retry.isdecimal() and len(retry) <= 10 else "unspecified"
    log.warning("provider=%s http_status=%s retry_after_seconds=%s", provider, response.status_code, seconds)
