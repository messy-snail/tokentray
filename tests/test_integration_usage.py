import threading
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from shiboken6 import isValid
from typer.testing import CliRunner

from tokentray.cli import app
from tokentray.core import i18n
from tokentray.core.config import Config
from tokentray.core.models import Snapshot, Status, UsageWindow
from tokentray.core.secrets import SecretStore
from tokentray.core.view import build_view
from tokentray.notify.preview import PreviewResult
from tokentray.ui.integration import IntegrationDialog

URL = "https://discord.com/api/webhooks/123/preview"


@pytest.fixture
def preview(qapp, qtbot, tmp_path, monkeypatch):
    config = Config({"webhook": {"kind": "discord"}}, tmp_path / "config.toml")
    store = SecretStore(tmp_path / "secrets.toml")
    monkeypatch.setattr(store, "_keyring", lambda: None)
    dialog = IntegrationDialog(config, on_saved=lambda _: pytest.fail("Must not save"), store=store)
    now = datetime.now(timezone.utc)
    views = [build_view(Snapshot(
        provider="claude", status=Status.OK,
        windows=[UsageWindow("claude.5h", 75, now + timedelta(minutes=30), 18000)],
    ), now)]
    calls = []

    def fetch(config, *, force):
        calls.append((threading.get_ident(), force, config.as_dict()))
        return views

    monkeypatch.setattr("tokentray.notify.preview.collect_views", fetch)
    dialog.url.setText(URL)
    dialog.show()
    yield dialog, views, calls
    if isValid(dialog):
        dialog.close()


def test_gui_and_cli_send_identical_cards_without_saving(preview, isolated_config, qtbot, webhook_payload):
    dialog, _, calls = preview
    before = dialog._config.as_dict()
    config = Config.load()
    config.set("webhook.kind", "discord")
    config.set("webhook.url", URL)
    config.save()
    with respx.mock:
        route = respx.post(URL).mock(return_value=httpx.Response(200, json={}))
        dialog.usage_button.click()
        qtbot.waitUntil(lambda: not dialog._busy)
        cli = CliRunner().invoke(app, ["webhook", "test", "--usage"])
    assert cli.exit_code == 0
    assert webhook_payload(route.calls[0].request) == webhook_payload(route.calls[1].request)
    assert calls[0][0] != threading.get_ident()
    assert calls[0][1] is True
    assert dialog._config.as_dict() == before
    assert dialog.status.text() == i18n.t("integration.usage_ok", n=1)


@pytest.mark.parametrize("kind,url", [
    ("discord", URL), ("slack", "https://hooks.slack.com/services/T/B/test"),
    ("ntfy", "https://ntfy.sh/test"), ("generic", "https://example.com/hook"),
])
def test_all_selected_destinations(preview, qtbot, kind, url):
    dialog, _, _ = preview
    dialog.kind.setCurrentIndex(dialog.kind.findData(kind))
    dialog.url.setText(url)
    with respx.mock:
        route = respx.post(url).mock(return_value=httpx.Response(200, text="ok"))
        dialog.usage_button.click()
        qtbot.waitUntil(lambda: not dialog._busy)
    assert route.call_count == 1
    assert dialog.status.text() == i18n.t("integration.usage_ok", n=1)


def test_connection_test_stays_separate(preview, qtbot, webhook_payload):
    dialog, _, calls = preview
    with respx.mock:
        route = respx.post(URL).mock(return_value=httpx.Response(200, json={}))
        dialog.test_button.click()
        qtbot.waitUntil(lambda: not dialog._busy)
    assert calls == []
    embed = webhook_payload(route.calls[0].request)["embeds"][0]
    assert "fields" not in embed
    assert dialog.status.text() == i18n.t("integration.test_ok")


@pytest.mark.parametrize("legacy", [False, True])
def test_saved_destination_is_used_when_input_empty(preview, qtbot, monkeypatch, legacy):
    from tokentray.notify.configuration import DestinationSettings

    dialog, _, _ = preview
    dialog._initial = DestinationSettings(False, "discord", True, URL if legacy else "")
    monkeypatch.setattr(dialog._store, "get", lambda key: URL)
    dialog.url.clear()
    with respx.mock:
        route = respx.post(URL).mock(return_value=httpx.Response(200, json={}))
        dialog.usage_button.click()
        qtbot.waitUntil(lambda: not dialog._busy)
    assert route.call_count == 1


@pytest.mark.parametrize("url", ["", "https://example.com/not-discord"])
def test_invalid_url_does_not_fetch(preview, url):
    dialog, _, calls = preview
    dialog.url.setText(url)
    dialog.usage_button.click()
    assert calls == []
    assert not dialog._busy
    assert dialog.status.text()


def test_empty_providers(preview, qtbot):
    dialog, views, _ = preview
    views.clear()
    with respx.mock:
        dialog.usage_button.click()
        qtbot.waitUntil(lambda: not dialog._busy)
    assert dialog.status.text() == i18n.t("integration.usage_empty")


def test_partial_failure_stops_and_reports_count(preview, qtbot):
    dialog, views, _ = preview
    views.extend([views[0], views[0]])
    with respx.mock:
        route = respx.post(URL).mock(side_effect=[httpx.Response(200), httpx.Response(403)])
        dialog.usage_button.click()
        qtbot.waitUntil(lambda: not dialog._busy)
    assert route.call_count == 2
    assert i18n.t("integration.usage_failed", n=1, reason="HTTP 403") in dialog.status.text()
    assert dialog.usage_button.isEnabled()


def test_fetch_exception_is_sanitized(preview, qtbot, monkeypatch):
    dialog, _, _ = preview

    def fail(*args, **kwargs):
        raise RuntimeError("private URL must not appear")

    monkeypatch.setattr("tokentray.notify.preview.collect_views", fail)
    dialog.usage_button.click()
    qtbot.waitUntil(lambda: not dialog._busy)
    assert "RuntimeError" in dialog.status.text()
    assert "private URL" not in dialog.status.text()


def test_sending_progress_keeps_ui_responsive(preview, qtbot, monkeypatch):
    from tokentray.notify.webhook import DeliveryResult

    dialog, _, _ = preview
    release = threading.Event()

    def deliver(hook, event):
        assert release.wait(3)
        return DeliveryResult(True)

    monkeypatch.setattr("tokentray.notify.webhook.Webhook.deliver", deliver)
    dialog.usage_button.click()
    try:
        qtbot.waitUntil(lambda: dialog.status.text() == i18n.t("integration.usage_sending"))
        assert dialog._busy
        assert not dialog.url.isEnabled()
        assert not dialog.kind.isEnabled()
    finally:
        release.set()
    qtbot.waitUntil(lambda: not dialog._busy)


@pytest.mark.parametrize("close_early", [False, True])
def test_async_progress_duplicate_clicks_and_deleted_dialog(preview, qtbot, monkeypatch, close_early):
    dialog, _, _ = preview
    release = threading.Event()
    finished = threading.Event()
    calls = []

    def send(config, hook, *, progress):
        calls.append(config)
        try:
            assert release.wait(3)
            progress("sending")
            return PreviewResult(sent=1)
        finally:
            finished.set()

    monkeypatch.setattr("tokentray.ui.integration.send_usage_preview", send)
    dialog.usage_button.click()
    try:
        qtbot.waitUntil(lambda: len(calls) == 1)
        assert dialog.status.text() == i18n.t("integration.usage_fetching")
        assert not dialog.usage_button.isEnabled()
        assert not dialog.test_button.isEnabled()
        assert not dialog.buttons.isEnabled()
        dialog._send_usage()
        dialog._test()
        assert len(calls) == 1
        assert calls[0] is not dialog._config
        if close_early:
            dialog.close()
            qtbot.waitUntil(lambda: not isValid(dialog))
    finally:
        release.set()
    qtbot.waitUntil(finished.is_set)
    if not close_early:
        qtbot.waitUntil(lambda: not dialog._busy)
        assert dialog.usage_button.isEnabled()
        assert dialog.status.text() == i18n.t("integration.usage_ok", n=1)
