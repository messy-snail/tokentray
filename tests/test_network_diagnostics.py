from __future__ import annotations

import logging
import socket
import ssl

import httpx
import pytest
import respx

from tokentray.core.models import Status
from tokentray.providers.claude import USAGE_URL, ClaudeProvider
from tokentray.providers.diagnostics import log_response, log_transport_error


@pytest.mark.parametrize(
    "cause,label",
    [
        (ssl.SSLCertVerificationError(1, "private certificate text"), "certificate_verification_failed"),
        (socket.gaierror(11001, "private hostname"), "dns_lookup_failed"),
        (ConnectionRefusedError(10061, "private proxy"), "connection_refused"),
        (httpx.ReadTimeout("private URL"), "timeout"),
        (ssl.SSLError(1, "private TLS text"), "tls_error"),
        (httpx.ProxyError("private password"), "proxy_error"),
    ],
)
def test_transport_cause_is_classified_without_exposing_text(caplog, cause, label):
    error = httpx.ConnectError("Bearer secret-token https://user:password@proxy/?token=secret")
    error.__cause__ = cause
    with caplog.at_level(logging.WARNING, logger="tokentray.network"):
        log_transport_error("claude", error)
    assert "provider=claude" in caplog.text
    assert "ConnectError" in caplog.text
    assert label in caplog.text
    for secret in ("Bearer", "secret-token", "password", "https://", "private"):
        assert secret not in caplog.text


def test_connect_error_is_logged_and_preserves_ui_and_backoff(config, cache, claude_credentials, caplog):
    provider = ClaudeProvider(config, cache)
    error = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] secret-token")
    try:
        with respx.mock:
            route = respx.get(USAGE_URL).mock(side_effect=error)
            snapshot = provider.fetch(now=1000)
            provider.fetch(now=1001)
            assert route.call_count == 1
        assert snapshot.status is Status.ERROR
        assert snapshot.detail == "ConnectError"
        assert "certificate_verification_failed" in caplog.text
        assert "secret-token" not in caplog.text
        assert sum("transport_failed" in r.message for r in caplog.records) == 1
    finally:
        provider.close()


def test_http_response_logs_status_and_retry_without_body_or_headers(config, cache, claude_credentials, caplog):
    provider = ClaudeProvider(config, cache)
    try:
        with respx.mock:
            respx.get(USAGE_URL).mock(return_value=httpx.Response(
                429, headers={"Retry-After": "3203", "Set-Cookie": "secret-cookie"},
                text="secret-body",
            ))
            assert provider.fetch().status is Status.RATE_LIMITED
        assert "http_status=429 retry_after_seconds=3203" in caplog.text
        assert "secret-cookie" not in caplog.text
        assert "secret-body" not in caplog.text
        assert "sk-test-token" not in caplog.text
    finally:
        provider.close()


def test_untrusted_retry_header_and_exception_cycles_are_safe(caplog):
    log_response("claude", httpx.Response(429, headers={"Retry-After": "secret-token"}))
    error = httpx.ConnectError("secret-token")
    error.__cause__ = error
    log_transport_error("claude", error)
    assert "retry_after_seconds=unspecified" in caplog.text
    assert "secret-token" not in caplog.text
    assert caplog.text.count("ConnectError") == 1


def test_successful_response_is_not_logged(caplog):
    log_response("claude", httpx.Response(200))
    assert not caplog.records


def test_diagnostics_reach_rotating_log_file(isolated_config):
    from tokentray.bootstrap import configure_logging
    from tokentray.core.paths import log_file

    logger = logging.getLogger("tokentray")
    previous_handlers, previous_level = logger.handlers[:], logger.level
    try:
        configure_logging()
        log_transport_error("claude", httpx.ConnectError("CERTIFICATE_VERIFY_FAILED secret-token"))
        content = log_file().read_text(encoding="utf-8")
        assert "startup version=" in content
        assert "standalone=False" in content
        assert "provider=claude transport_failed" in content
        assert "certificate_verification_failed" in content
        assert "secret-token" not in content
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers = previous_handlers
        logger.setLevel(previous_level)
