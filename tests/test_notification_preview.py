"""Fresh previews are isolated from automatic alerts and run off the UI thread."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent, QThread

from tokentray import ipc
from tokentray.app import Controller
from tokentray.core import i18n
from tokentray.core.alerts import AlertState
from tokentray.core.config import Config
from tokentray.core.models import Snapshot, Status, UsageWindow
from tokentray.core.view import build_view
from tokentray.notify.formatting import usage_preview
from tokentray.polling import PollWorker
from tokentray.ui.tray import Tray


def snapshot(provider="claude", status=Status.OK):
    reset = datetime.now(timezone.utc) + timedelta(hours=2)
    return Snapshot(provider, status, windows=[
        UsageWindow(f"{provider}.5h", 27, reset, 5 * 3600),
        UsageWindow(f"{provider}.7d", 46, reset, 7 * 86400),
    ] if status.has_data else [])


@pytest.mark.parametrize("language", ["en", "ko"])
def test_preview_uses_real_values_and_provider_order(language):
    i18n.set_language(language)
    views = [build_view(snapshot("codex")), build_view(snapshot())]
    result = usage_preview(views, disabled=set())
    lines = result.body.splitlines()
    assert result.title == i18n.t("test.title")
    assert lines[0].startswith("Claude Code:")
    assert lines[1].startswith("Codex:")
    for line, view in zip(lines, reversed(views)):
        assert "73%" in line and "54%" in line
        assert line.index(view.rows[0].label) < line.index(view.rows[1].label)


@pytest.mark.parametrize("status", [Status.EXPIRED, Status.UNAUTHORIZED,
                                    Status.NOT_CONFIGURED, Status.ERROR, Status.RATE_LIMITED])
def test_partial_failure_preserves_success(status):
    failed = build_view(snapshot("codex", status))
    result = usage_preview([build_view(snapshot()), failed], disabled=set())
    assert "73%" in result.body.splitlines()[0]
    assert result.body.splitlines()[1] == f"Codex: {failed.message}"
    assert "%" not in result.body.splitlines()[1]


@pytest.mark.parametrize("status", [Status.CACHED, Status.STALE])
def test_cached_data_is_explicit(status):
    result = usage_preview([build_view(snapshot(status=status))], disabled=set())
    assert i18n.t("test.previous_data") in result.body
    assert "73%" in result.body


def test_empty_disabled_and_missing_data():
    empty = build_view(Snapshot("claude", Status.OK))
    result = usage_preview([empty], disabled={"codex"})
    assert i18n.t("status.no_data") in result.body
    assert f"Codex: {i18n.t('test.disabled')}" in result.body
    assert "%" not in result.body
    assert usage_preview([], disabled=set()).body.count(i18n.t("status.no_data")) == 2


def test_both_failed():
    views = [build_view(snapshot(p, Status.ERROR)) for p in ("claude", "codex")]
    result = usage_preview(views, disabled=set())
    assert result.body.count(i18n.t("status.api_error")) == 2
    assert "%" not in result.body


@pytest.fixture
def controller(qapp, monkeypatch):
    from tokentray.ui import popup

    monkeypatch.setattr(popup, "Toast", lambda **kwargs: kwargs)
    obj = SimpleNamespace(
        _test_pending=False, _worker=Mock(), tray=Mock(), panel=Mock(), recovery=Mock(),
        dispatcher=Mock(), config=Config(), views=[], alerts=AlertState(seeded=True),
        _state={"sentinel": True}, _save_state=Mock(),
    )
    obj._update_views = lambda snapshots: Controller._update_views(obj, snapshots)
    obj.show_test_alert = lambda: Controller.show_test_alert(obj)
    return obj


def test_requests_merge_and_do_not_finish_on_normal_poll(controller):
    controller.show_test_alert()
    controller.show_test_alert()
    Controller._handle_command(controller, ipc.CMD_TEST)
    controller._worker.test_requested.emit.assert_called_once_with()
    controller.dispatcher.present.assert_not_called()
    Controller._on_snapshots(controller, [snapshot()])
    assert controller._test_pending
    controller.dispatcher.present.assert_not_called()
    Controller._on_test_finished(controller, [snapshot(), snapshot("codex")])
    assert not controller._test_pending
    assert controller.tray.set_test_pending.call_args.args == (False,)
    controller.dispatcher.present.assert_called_once()
    Controller._on_test_finished(controller, [])
    controller.dispatcher.present.assert_called_once()
    controller.show_test_alert()
    assert controller._worker.test_requested.emit.call_count == 2


def test_preview_updates_views_without_automatic_alert_side_effects(controller):
    controller.show_test_alert()
    before = deepcopy(controller.alerts.to_dict()), deepcopy(controller._state)
    Controller._on_test_finished(controller, [snapshot(), snapshot("codex")])
    assert before == (controller.alerts.to_dict(), controller._state)
    controller._save_state.assert_not_called()
    controller.dispatcher.emit.assert_not_called()
    controller.recovery.on_views.assert_called_once_with(controller.views)
    controller.panel.update_views.assert_called_once_with(controller.views)
    controller.tray.update_views.assert_called_once_with(controller.views)
    assert "73%" in controller.dispatcher.present.call_args.args[1]


def test_worker_failure_restores_menu_without_reusing_old_views(controller):
    controller.views = [build_view(snapshot())]
    controller.show_test_alert()
    Controller._on_test_finished(controller, None)
    assert controller.dispatcher.present.call_args.args[:2] == (
        i18n.t("test.title"), i18n.t("test.failed"))
    assert not controller._test_pending
    assert controller.tray.set_test_pending.call_args.args == (False,)


def test_pending_menu_survives_language_rebuild(qapp):
    tray = Tray()
    tray.set_test_pending(True)
    i18n.set_language("ko")
    tray.retranslate()
    assert not tray._test_action.isEnabled()
    assert tray._test_action.text() == i18n.t("test.loading")
    tray.set_test_pending(False)
    assert tray._test_action.isEnabled()
    assert tray._test_action.text() == i18n.t("menu.test_alert")


def test_custom_preview_has_a_meter_for_each_limit(qapp):
    from PySide6.QtWidgets import QLabel

    from tokentray.ui.fonts import initialize_fonts
    from tokentray.ui.popup import ToastManager, _Meter
    from tokentray.ui.provider_icons import ProviderMark

    initialize_fonts(qapp)
    manager = ToastManager()
    shown = []
    manager.show = shown.append
    views = [build_view(snapshot()), build_view(snapshot("codex", Status.CACHED))]
    try:
        manager.show_usage_preview(views, disabled=set())
        assert len(shown) == 2
        for card, view in zip(shown, views):
            assert card.findChild(ProviderMark).provider == view.provider
            assert [meter._fraction for meter in card.findChildren(_Meter)] == [0.73, 0.54]
            labels = "\n".join(label.text() for label in card.findChildren(QLabel))
            for row in view.rows:
                assert row.label in labels
                assert row.remaining_text in labels
        assert i18n.t("test.previous_data") in "\n".join(
            label.text() for label in shown[1].findChildren(QLabel))
    finally:
        for card in shown:
            card.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_disabled_and_failed_preview_have_no_fake_meters(qapp):
    from PySide6.QtWidgets import QLabel

    from tokentray.ui.fonts import initialize_fonts
    from tokentray.ui.popup import ToastManager, _Meter

    initialize_fonts(qapp)
    manager = ToastManager()
    shown = []
    manager.show = shown.append
    try:
        manager.show_usage_preview([build_view(snapshot("claude", Status.ERROR))], disabled={"codex"})
        assert len(shown) == 2
        assert all(not card.findChildren(_Meter) for card in shown)
        assert i18n.t("test.disabled") in "\n".join(
            label.text() for label in shown[1].findChildren(QLabel))
    finally:
        for card in shown:
            card.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_worker_exceptions_preserve_other_provider(qapp, isolated_config, monkeypatch):
    from tokentray import providers

    good = snapshot("codex")
    failed = SimpleNamespace(id="claude", fetch=Mock(side_effect=RuntimeError("failed")))
    succeeds = SimpleNamespace(id="codex", fetch=Mock(return_value=good))
    monkeypatch.setattr(providers, "build_providers", lambda *args: [failed, succeeds])
    worker = PollWorker(Config())
    completed, regular = [], []
    worker.test_finished.connect(completed.append)
    worker.snapshots_ready.connect(regular.append)
    worker._run_test()
    assert len(completed) == 1
    assert completed[0][0].status == Status.ERROR
    assert completed[0][1] is good
    assert regular == []
    failed.fetch.assert_called_once_with(force=True)
    succeeds.fetch.assert_called_once_with(force=True)


def test_test_waits_for_normal_poll_on_worker_thread(qapp, qtbot, isolated_config, monkeypatch):
    from tokentray import providers

    entered, release = Event(), Event()
    calls = []

    def fetch(*, force):
        calls.append((force, QThread.currentThread()))
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        return snapshot()

    monkeypatch.setattr(providers, "build_providers", lambda *args: [
        SimpleNamespace(id="claude", fetch=fetch)])
    worker = PollWorker(Config())
    thread = QThread()
    worker.moveToThread(thread)
    thread.finished.connect(worker.deleteLater)
    regular, completed = [], []
    worker.snapshots_ready.connect(regular.append)
    worker.test_finished.connect(completed.append)
    thread.start()
    try:
        worker.requested.emit(False)
        qtbot.waitUntil(entered.is_set)
        worker.test_requested.emit()
        assert completed == []
        release.set()
        qtbot.waitUntil(lambda: len(completed) == 1)
        assert len(regular) == 1
        assert [force for force, _ in calls] == [False, True]
        assert all(t == thread for _, t in calls)
    finally:
        release.set()
        thread.quit()
        assert thread.wait(4000)
