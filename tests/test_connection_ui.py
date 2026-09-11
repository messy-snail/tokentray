from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QPushButton

from tokentray.connections import AuthState, Connection
from tokentray.core import i18n
from tokentray.core.alerts import AlertEvent, AlertState, _status_events
from tokentray.core.models import Snapshot, Status
from tokentray.core.view import build_view
from tokentray.ui.panel import DetailPanel
from tokentray.ui.popup import Toast, ToastManager, MAX_VISIBLE, SHADOW_MARGIN, GAP


@pytest.mark.parametrize("language", ["en", "ko"])
def test_panel_auth_actions_and_status(qapp, language):
    i18n.set_language(language)
    panel = DetailPanel(lambda: None)
    panel.recovery = SimpleNamespace(
        sessions={"claude": SimpleNamespace(waiting=False, message="")},
        message=lambda key: i18n.t("connect.hint", provider="Claude Code"),
        actions=lambda key: [(i18n.t("connect.login"), lambda: None)],
    )
    try:
        panel.update_views([build_view(Snapshot(provider="claude", status=Status.EXPIRED))])
        panel.popup_at(QRect(500, 500, 20, 20))
        assert any(b.text() == i18n.t("connect.login") for b in panel.findChildren(QPushButton))
        panel.update_views([build_view(Snapshot(provider="claude", status=Status.OK))])
        assert not any(b.property("connection-action") for b in panel.findChildren(QPushButton))
    finally:
        panel.close()


def test_auth_action_is_not_inferred_from_text():
    for status, expected in [(Status.EXPIRED, True), (Status.UNAUTHORIZED, True), (Status.SCHEMA_CHANGED, False)]:
        view = build_view(Snapshot(provider="claude", status=status))
        view.message = "same arbitrary translated message"
        events = _status_events(view, AlertState())
        assert events[0].login_required is expected


def test_toast_button_does_not_activate_body(qapp, qtbot):
    actions, bodies = [], []
    toast = Toast(title="test", body="expired", actions=[("Log in", lambda: actions.append(True))])
    toast.activated.connect(lambda: bodies.append(True))
    toast.present(QPoint(0, 0), slide_from=0)
    try:
        button = next(b for b in toast.findChildren(QPushButton) if b.text() == "Log in")
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert actions == [True]
        assert bodies == []
    finally:
        toast.close()


def test_toast_body_opens_detail(qapp, qtbot):
    calls = []
    toast = Toast(title="test", body="expired")
    toast.activated.connect(lambda: calls.append(True))
    toast.present(QPoint(0, 0), slide_from=0)
    try:
        qtbot.mouseClick(toast, Qt.MouseButton.LeftButton, pos=QPoint(SHADOW_MARGIN + 5, SHADOW_MARGIN + 5))
        assert calls == [True]
    finally:
        toast.close()


def test_summary_toast_has_no_provider_login_action(qapp):
    manager = ToastManager()
    requested = []
    manager.login_actions = lambda key: requested.append(key) or [("Log in", lambda: None)]
    events = [AlertEvent(kind="info", key=str(n), title="test", body="expired",
                         provider="claude", login_required=True) for n in range(MAX_VISIBLE + 1)]
    try:
        manager.show_alerts(events)
        assert requested == []
        manager.show_alerts(events[:1])
        assert requested == ["claude"]
    finally:
        for toast in list(manager._toasts):
            toast.close()


@pytest.mark.parametrize("kind", ["panel", "toast"])
def test_shadow_bounds_fit_inside_window(qapp, kind):
    widget = DetailPanel(lambda: None) if kind == "panel" else Toast(title="test", body="test")
    try:
        widget.show()
        qapp.processEvents()
        card = next(w for w in widget.findChildren(QFrame) if isinstance(w.graphicsEffect(), QGraphicsDropShadowEffect))
        bounds = card.graphicsEffect().boundingRectFor(QRectF(card.rect()))
        bounds.translate(card.pos())
        assert QRectF(widget.rect()).contains(bounds)
    finally:
        widget.close()


def test_stack_card_gap_is_independent_of_shadow_margin(qapp):
    manager = ToastManager()
    first = Toast(title="a", body="one")
    second = Toast(title="b", body="two")
    manager._toasts = [first, second]
    try:
        area = QRect(0, 0, 1000, 1000)
        first_pos = manager._slot(0, first, area, True)
        second_pos = manager._slot(1, second, area, True)
        assert second_pos.y() - first_pos.y() == first.height() - 2 * SHADOW_MARGIN + GAP
    finally:
        first.close()
        second.close()
