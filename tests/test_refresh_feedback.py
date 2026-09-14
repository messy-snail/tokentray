from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QPushButton

from tokentray.core import i18n
from tokentray.core.config import Config
from tokentray.core.models import Snapshot, Status
from tokentray.core.refresh import RefreshResult
from tokentray.core.view import build_view
from tokentray.ui import refresh_feedback
from tokentray.ui.panel import DetailPanel


def result(success=True):
    return RefreshResult.from_snapshots([Snapshot(provider="claude", status=Status.OK if success else Status.ERROR)])


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
        panel.refresh_feedback.finish(result())
        qtbot.waitUntil(lambda: panel._refresh_status.text() == result().text, timeout=1500)
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
        panel.refresh_feedback.finish(result(success))
        assert panel.refresh_feedback.busy
        qtbot.waitUntil(lambda: panel.refresh_feedback.state == key, timeout=1000)
        assert panel._refresh_status.text() == result(success).text
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
        panel.refresh_feedback.finish(result())
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
    assert [item.successful for item in results] == expected


@pytest.mark.parametrize("statuses, expected", [
    ([Status.OK, Status.NOT_CONFIGURED], [True]),
    ([Status.NOT_CONFIGURED, Status.NOT_CONFIGURED], [False]),
    ([Status.OK, Status.ERROR], [False]),
    ([Status.NOT_CONFIGURED, Status.EXPIRED], [False]),
])
def test_a_service_nobody_signed_in_to_does_not_fail_the_refresh(
    qapp, isolated_config, monkeypatch, statuses, expected
):
    from tokentray import providers
    from tokentray.app import PollWorker

    fakes = [
        SimpleNamespace(fetch=lambda status=status, **kw: Snapshot(provider="claude", status=status))
        for status in statuses
    ]
    monkeypatch.setattr(providers, "build_providers", lambda *a: fakes)
    worker = PollWorker(Config({}))
    results = []
    worker.refresh_finished.connect(results.append)
    worker._run(True)
    assert [item.successful for item in results] == expected


def test_unexpected_worker_exception_ends_refresh(qapp, isolated_config, monkeypatch):
    from tokentray import providers
    from tokentray.app import PollWorker

    def fail(**kwargs):
        raise RuntimeError("test failure")
    monkeypatch.setattr(providers, "build_providers", lambda *a: [SimpleNamespace(id="claude", fetch=fail)])
    worker = PollWorker(Config({}))
    results = []
    worker.refresh_finished.connect(results.append)
    worker._run(True)
    assert [item.successful for item in results] == [False]
    assert results[0].providers[0].provider == "claude"


@pytest.mark.parametrize("language", ["en", "ko"])
@pytest.mark.parametrize("failed_provider", ["claude", "codex"])
def test_partial_failure_names_service_and_preserves_reason(language, failed_provider):
    i18n.set_language(language)
    snapshots = [Snapshot(provider=key, status=Status.OK) for key in ("claude", "codex")]
    failed = next(s for s in snapshots if s.provider == failed_provider)
    failed.status = Status.STALE
    failed.failure_kind = "rate_limited"
    failed.retry_at = 1900000000
    summary = RefreshResult.from_snapshots(snapshots)
    name = "Claude" if failed_provider == "claude" else "Codex"
    assert i18n.t("refresh.provider_failed", provider=name, reason=i18n.t("refresh.reason_limited")) in summary.text
    assert "updated" in summary.text if language == "en" else "갱신 완료" in summary.text
    failed.request_skipped = True
    assert i18n.t("refresh.provider_waiting", provider=name) in RefreshResult.from_snapshots(snapshots).text


@pytest.mark.parametrize("language", ["en", "ko"])
def test_long_feedback_wraps_above_button_and_survives_rebuild(qapp, qtbot, language):
    from datetime import datetime, timezone

    from tokentray.core.models import UsageWindow

    i18n.set_language(language)
    limited = Snapshot(
        provider="claude", status=Status.STALE, failure_kind="rate_limited", retry_at=1900000000,
        fetched_at=1800000000, windows=[UsageWindow("claude.5h", 20, datetime(2030, 1, 1, tzinfo=timezone.utc), 18000)],
    )
    other = Snapshot(provider="codex", status=Status.UNREADABLE)
    summary = RefreshResult.from_snapshots([limited, other])
    views = [build_view(limited), build_view(other)]
    panel = DetailPanel(lambda: None)
    try:
        panel.update_views(views)
        panel.popup_at(None)
        panel._refresh_clicked()
        panel.refresh_feedback.finish(summary)
        qtbot.waitUntil(lambda: panel.refresh_feedback.state == "failed", timeout=1500)
        panel.update_views(views)
        qtbot.waitUntil(lambda: panel._refresh_button.geometry().top() > 0, timeout=1000)
        assert panel._refresh_status.text() == summary.text
        assert panel._refresh_status.wordWrap()
        assert panel._refresh_status.geometry().bottom() < panel._refresh_button.geometry().top()
        assert panel._refresh_status.height() >= panel._refresh_status.heightForWidth(panel._refresh_status.width())
        assert ("요청 제한" if language == "ko" else "Rate limited") in views[0].message
        assert "마지막 갱신" in views[0].message if language == "ko" else "Last updated" in views[0].message
        assert panel.refresh_feedback._reset.interval() == 5000
    finally:
        panel.close()
        panel.deleteLater()


def test_provider_exception_does_not_stop_other_provider(qapp, monkeypatch):
    from tokentray import providers
    from tokentray.polling import PollWorker

    def fail(**kwargs):
        raise RuntimeError("private text")

    monkeypatch.setattr(providers, "build_providers", lambda *a: [
        SimpleNamespace(id="claude", fetch=fail),
        SimpleNamespace(id="codex", fetch=lambda **kw: Snapshot(provider="codex", status=Status.OK)),
    ])
    worker = PollWorker(Config({}))
    results = []
    worker.refresh_finished.connect(results.append)
    worker._run(True)
    assert [(p.provider, p.outcome) for p in results[0].providers] == [("claude", "failed"), ("codex", "done")]
