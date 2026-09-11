from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QPushButton

from tokentray.core import i18n
from tokentray.core.config import Config
from tokentray.core.models import Snapshot, Status
from tokentray.core.view import build_view
from tokentray.ui.panel import DetailPanel
from tokentray.ui import refresh_feedback


@pytest.mark.parametrize("language", ["en", "ko"])
def test_refresh_animates_and_survives_data_rebuild(qapp, qtbot, language):
    i18n.set_language(language)
    requests = []
    panel = DetailPanel(lambda: requests.append(True))
    try:
        panel.popup_at(None)
        button = panel.findChild(QPushButton, "panel-refresh")
        button.click()
        first_width = button.width()
        assert button.text() == i18n.t("menu.refresh")
        assert panel.loading_overlay.isVisible()
        first_angle = panel.loading_overlay._angle
        assert not button.isEnabled()
        button.click()
        assert requests == [True]
        qtbot.waitUntil(lambda: panel.loading_overlay._angle != first_angle, timeout=1000)
        assert button.width() == first_width
        panel.update_views([build_view(Snapshot(provider="claude", status=Status.OK))])
        button = panel.findChild(QPushButton, "panel-refresh")
        assert not button.isEnabled()
        assert button.text() == i18n.t("menu.refresh")
        assert panel.loading_overlay.isVisible()
        panel.refresh_feedback.finish(True)
        qtbot.waitUntil(lambda: panel._refresh_status.text() == i18n.t("refresh.done"), timeout=1500)
        assert not panel.loading_overlay.isVisible()
        assert not panel.loading_overlay._timer.isActive()
        assert button.isEnabled()
        assert panel.isVisible()
    finally:
        panel.close()
        panel.deleteLater()


@pytest.mark.parametrize("success, key", [(True, "done"), (False, "failed")])
def test_fast_result_is_visible_then_returns_to_refresh(qapp, qtbot, monkeypatch, success, key):
    monkeypatch.setattr(refresh_feedback, "MIN_BUSY_MS", 30)
    monkeypatch.setattr(refresh_feedback, "RESULT_MS", 100)
    panel = DetailPanel(lambda: None)
    try:
        panel._refresh_clicked()
        panel.refresh_feedback.finish(success)
        assert panel.refresh_feedback.busy
        qtbot.waitUntil(lambda: panel.refresh_feedback.state == key, timeout=1000)
        assert panel._refresh_status.text() == i18n.t("refresh." + key)
        assert panel._refresh_button.text() == i18n.t("menu.refresh")
        qtbot.waitUntil(lambda: panel.refresh_feedback.state == "idle", timeout=1000)
        assert panel._refresh_button.text() == i18n.t("menu.refresh")
        assert panel._refresh_status.text() == ""
        assert not panel.isVisible()
    finally:
        panel.deleteLater()


def test_overlay_stays_inside_card_and_stops_when_closed(qapp, qtbot):
    from PySide6.QtCore import QPoint, Qt
    from tokentray.ui.popup import SHADOW_MARGIN

    requests = []
    panel = DetailPanel(lambda: requests.append(True))
    try:
        panel.popup_at(None)
        panel._refresh_clicked()
        assert panel.loading_overlay.geometry() == panel.rect().adjusted(
            SHADOW_MARGIN, SHADOW_MARGIN, -SHADOW_MARGIN, -SHADOW_MARGIN)
        qtbot.mouseClick(panel.loading_overlay, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
        assert requests == [True]
        assert panel.isVisible()
        panel.close()
        assert not panel.loading_overlay._timer.isActive()
        panel.refresh_feedback.finish(True)
        qtbot.waitUntil(lambda: panel.refresh_feedback.state == "done", timeout=1500)
        assert not panel.isVisible()
    finally:
        panel.deleteLater()


@pytest.mark.parametrize("force, status, expected", [
    (False, Status.OK, []),
    (True, Status.OK, [True]),
    (True, Status.ERROR, [False]),
    (True, Status.STALE, [False]),
    (True, Status.RATE_LIMITED, [False]),
])
def test_worker_completion_reports_actual_result(qapp, isolated_config, monkeypatch, force, status, expected):
    from tokentray import providers
    from tokentray.app import PollWorker

    snapshot = Snapshot(provider="claude", status=status)
    monkeypatch.setattr(providers, "build_providers", lambda *a: [SimpleNamespace(fetch=lambda **kw: snapshot)])
    worker = PollWorker(Config({}))
    results = []
    worker.refresh_finished.connect(results.append)
    worker._run(force)
    assert results == expected


def test_unexpected_worker_exception_ends_refresh(qapp, isolated_config, monkeypatch):
    from tokentray import providers
    from tokentray.app import PollWorker

    def fail(**kwargs):
        raise RuntimeError("test failure")
    monkeypatch.setattr(providers, "build_providers", lambda *a: [SimpleNamespace(fetch=fail)])
    worker = PollWorker(Config({}))
    results = []
    worker.refresh_finished.connect(results.append)
    worker._run(True)
    assert results == [False]
