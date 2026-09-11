"""Local channel selection must not duplicate Windows banners or webhook sends."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("PySide6")

from tokentray.core.alerts import AlertEvent
from tokentray.notify.dispatcher import Dispatcher
from tokentray.ui.popup import MAX_VISIBLE


@pytest.fixture
def routing(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    cards, webhook, native = Mock(), Mock(), Mock(return_value=True)
    dispatcher = Dispatcher(cards, webhook, native=native)
    return dispatcher, cards, webhook, native


def events(count=2):
    return [AlertEvent("info", str(i), f"title {i}", "body") for i in range(count)]


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("count", [0, 2, MAX_VISIBLE + 1])
def test_channels_and_webhook(routing, monkeypatch, platform, enabled, count):
    dispatcher, cards, webhook, native = routing
    monkeypatch.setattr(sys, "platform", platform)
    dispatcher.set_native_enabled(enabled)
    batch = events(count)
    dispatcher.emit(batch)
    messages = 1 if count > MAX_VISIBLE else count
    assert native.call_count == (messages if enabled else 0)
    assert cards.show_alerts.called == (bool(count) and (platform != "win32" or not enabled))
    assert webhook.send.call_count == (count if count <= MAX_VISIBLE else 0)
    assert webhook.send_summary.call_count == int(count > MAX_VISIBLE)


@pytest.mark.parametrize("result", [False, RuntimeError("submission failed")])
def test_only_failed_event_falls_back(routing, result):
    dispatcher, cards, webhook, native = routing
    batch = events()
    native.side_effect = [True, result]
    dispatcher.emit(batch)
    cards.show_alerts.assert_called_once_with([batch[1]])
    assert webhook.send.call_count == 2


def test_summary_failure_falls_back_to_original_batch(routing):
    dispatcher, cards, webhook, native = routing
    native.return_value = False
    batch = events(MAX_VISIBLE + 1)
    dispatcher.emit(batch)
    cards.show_alerts.assert_called_once_with(batch)
    native.assert_called_once()
    webhook.send_summary.assert_called_once()


@pytest.mark.parametrize("count", [2, MAX_VISIBLE + 1])
def test_login_batch_keeps_custom_presentation(routing, count):
    dispatcher, cards, webhook, native = routing
    batch = events(count)
    batch[0].login_required = True
    batch[0].provider = "claude"
    dispatcher.emit(batch)
    cards.show_alerts.assert_called_once_with(batch)
    native.assert_not_called()
    assert webhook.send.called or webhook.send_summary.called


def test_missing_callback_falls_back():
    cards = Mock()
    dispatcher = Dispatcher(cards, Mock())
    dispatcher.emit(events(1))
    cards.show_alerts.assert_called_once()


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
@pytest.mark.parametrize("enabled, succeeds", [(True, True), (False, True), (True, False)])
def test_test_notification_presentation(routing, qapp, monkeypatch, platform, enabled, succeeds):
    from tokentray.app import Controller
    from tokentray.ui import popup

    dispatcher, cards, webhook, native = routing
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(popup, "Toast", lambda **kwargs: kwargs)
    dispatcher.set_native_enabled(enabled)
    native.return_value = succeeds
    from tokentray.core.config import Config
    controller = SimpleNamespace(dispatcher=dispatcher, toasts=cards,
                                 config=Config(), tray=Mock(), views=[],
                                 _test_pending=True, _update_views=Mock())
    Controller._on_test_finished(controller, [])
    assert native.call_count == int(enabled)
    assert cards.show_usage_preview.call_count == (0 if platform == "win32" and enabled and succeeds else 1)
    assert not webhook.mock_calls


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_welcome_keeps_actions(routing, qapp, monkeypatch, platform):
    from tokentray.app import Controller
    from tokentray.ui import popup

    dispatcher, cards, _, native = routing
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(popup, "Toast", lambda **kwargs: kwargs)
    controller = SimpleNamespace(dispatcher=dispatcher, toasts=cards, _state={}, _save_state=Mock())
    Controller._show_welcome(controller)
    assert cards.show.call_args.args[0]["actions"]
    assert cards.show.call_args.args[0]["sticky"] is True
    assert native.call_count == int(platform != "win32")
    assert controller._state["welcomed"] is True


def test_config_reload_changes_delivery(routing, qapp, isolated_config):
    from tokentray.app import Controller
    from tokentray.core import paths
    from tokentray import ipc

    dispatcher, cards, webhook, native = routing
    controller = SimpleNamespace(dispatcher=dispatcher, toasts=cards, webhook=webhook,
                                 alerts=Mock(), views=[])
    dispatcher.emit(events(1))
    cards.show_alerts.assert_not_called()
    paths.config_file().write_text('native_notifications = false\n', encoding="utf-8")
    Controller._handle_command(controller, ipc.CMD_RELOAD_CONFIG)
    dispatcher.emit(events(1))
    cards.show_alerts.assert_called_once()
    assert native.call_count == 1


def test_unsupported_windows_host_does_not_submit(qapp, monkeypatch):
    from tokentray.ui import tray

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(tray, "supports_messages", lambda: False)
    instance = tray.Tray()
    submit = Mock()
    monkeypatch.setattr(instance._icon, "showMessage", submit)
    assert instance.show_message("title", "body") is False
    submit.assert_not_called()
