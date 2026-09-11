"""Structured panel fields and geometry across languages and screen sizes."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QLabel, QPushButton

from tokentray.core import compute, i18n
from tokentray.core.models import Snapshot, Status, UsageWindow
from tokentray.core.view import build_view
from tokentray.ui.fonts import initialize_fonts
from tokentray.ui.panel import DetailPanel

NOW = datetime(2026, 9, 10, 3, 0, tzinfo=timezone.utc)


def views():
    return [
        build_view(Snapshot(provider=provider, status=Status.OK, windows=[
            UsageWindow(key=f"{provider}.{hours}", used_pct=58,
                        resets_at=NOW + timedelta(hours=hours / 2),
                        window_secs=hours * 3600)
            for hours in durations
        ]), NOW)
        for provider, durations in (("claude", (5, 168)), ("codex", (168,)))
    ]


def settle(qapp):
    for _ in range(15):
        qapp.processEvents()


@pytest.fixture(autouse=True)
def keep_alive(qapp):
    previous = qapp.quitOnLastWindowClosed()
    qapp.setQuitOnLastWindowClosed(False)
    initialize_fonts(qapp)
    yield
    settle(qapp)
    qapp.setQuitOnLastWindowClosed(previous)


@pytest.mark.parametrize("language", ["ko", "en"])
def test_details_preserve_existing_text(language):
    i18n.set_language(language)
    for view in views():
        for row in view.rows:
            details = {item.key: item for item in row.details}
            assert list(details) == ["refills", "burns", "pace"]
            assert row.refills == f"{details['refills'].label} {details['refills'].value}"
            assert row.burns == f"{details['burns'].label} {details['burns'].value}"
            assert details["pace"].value == f"{row.stats.pace}x {row.pace_icon}".strip()
            assert row.pace == i18n.t("fmt.pace", pace=row.stats.pace)


def test_missing_and_reset_values():
    window = UsageWindow(key="claude.5h", used_pct=0, resets_at=None, window_secs=18000)
    snapshot = Snapshot(provider="claude", status=Status.OK, windows=[window])
    row = build_view(snapshot, NOW).rows[0]
    assert row.details == []
    snapshot = replace(
        snapshot,
        windows=[replace(window, resets_at=NOW - timedelta(seconds=1))],
        window_reset_pending=True,
    )
    row = build_view(snapshot, NOW).rows[0]
    assert row.details == []
    assert row.detail_status == i18n.t("status.window_reset")
    assert row.remaining_text == "~0%"


@pytest.mark.parametrize("language", ["ko", "en"])
@pytest.mark.parametrize("height", [360, 900])
def test_panel_columns_and_scroll(qapp, monkeypatch, language, height):
    i18n.set_language(language)
    monkeypatch.setattr(compute, "format_local_reset", lambda *_: "September 12 11:59:59 PM (local time)")
    panel = DetailPanel(on_refresh=lambda: None)
    panel.update_views(views())
    panel._rebuild()
    panel._fit_to_area(QRect(0, 0, 800, height))
    panel.show()
    settle(qapp)
    labels = [w for w in panel.findChildren(QLabel) if w.property("detail-role") == "label"]
    values = [w for w in panel.findChildren(QLabel) if w.property("detail-role") == "value"]
    assert len(labels) == len(values) == 9
    sources = [w for w in panel.findChildren(QLabel) if w.property("panel-source")]
    assert len(sources) == 2
    assert all(w.width() >= w.fontMetrics().horizontalAdvance(w.text()) for w in sources)
    assert len({w.mapTo(panel, QPoint()).x() for w in values}) == 1
    for label, value in zip(labels, values):
        assert label.mapTo(panel, QPoint()).y() == value.mapTo(panel, QPoint()).y()
        assert value.mapTo(panel, QPoint()).x() >= label.mapTo(panel, QPoint(label.width(), 0)).x() + 8
        assert value.height() >= value.heightForWidth(value.width())
        if value.property("detail-key") == "pace":
            assert not value.wordWrap()
            assert value.fontMetrics().horizontalAdvance(value.text()) <= value.width()
    assert panel.scroll.horizontalScrollBar().maximum() == 0
    assert panel.height() <= height
    scrollbar = panel.scroll.verticalScrollBar()
    if height == 360:
        assert scrollbar.maximum() > 0
    else:
        assert scrollbar.maximum() == 0
    scrollbar.setValue(scrollbar.maximum())
    settle(qapp)
    last = values[-1]
    assert last.mapTo(panel.scroll.viewport(), QPoint(0, last.height())).y() <= panel.scroll.viewport().height()
    refresh = panel.findChild(QPushButton, "panel-refresh")
    assert refresh.mapTo(panel, QPoint(0, refresh.height())).y() < panel.height()
    panel.close()


def test_refresh_repositions_and_keeps_button_working(qapp):
    refreshed = []
    panel = DetailPanel(on_refresh=lambda: refreshed.append(True))
    panel.popup_at(QRect(10, 10, 24, 24))
    panel.update_views(views())
    settle(qapp)
    area = panel.screen().availableGeometry()
    assert area.contains(panel.geometry())
    panel.findChild(QPushButton, "panel-refresh").click()
    assert refreshed == [True]
    assert panel.isVisible()
    updated = views()
    updated[0].rows[0].remaining_text = "17%"
    panel.update_views(updated)
    settle(qapp)
    assert panel.isVisible()
    assert any(label.text() == "17%" for label in panel.findChildren(QLabel))
    assert area.contains(panel.geometry())
    panel.close()


def test_refresh_result_does_not_reopen_dismissed_panel(qapp):
    refreshed = []
    panel = DetailPanel(on_refresh=lambda: refreshed.append(True))
    panel.update_views(views())
    panel.popup_at(None)
    panel.findChild(QPushButton, "panel-refresh").click()
    assert refreshed == [True]
    assert panel.isVisible()
    panel.close()
    updated = views()
    updated[0].rows[0].remaining_text = "17%"
    panel.update_views(updated)
    settle(qapp)
    assert not panel.isVisible()
    panel.popup_at(None)
    settle(qapp)
    assert any(label.text() == "17%" for label in panel.findChildren(QLabel))
    panel.close()


def test_reset_status_spans_detail_area(qapp):
    view = views()[0]
    view.rows = [build_view(Snapshot(
        provider="claude", status=Status.OK, window_reset_pending=True,
        windows=[UsageWindow(key="claude.5h", used_pct=50,
                             resets_at=NOW - timedelta(seconds=1), window_secs=18000)],
    ), NOW).rows[0]]
    panel = DetailPanel(on_refresh=lambda: None)
    panel.update_views([view])
    panel.popup_at(None)
    settle(qapp)
    labels = panel.content.findChildren(QLabel)
    status = next(w for w in labels if w.text() == i18n.t("status.window_reset"))
    assert status.width() == panel.content.width()
    assert not any(w.property("detail-role") for w in labels)
    panel.close()
