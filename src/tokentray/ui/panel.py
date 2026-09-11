"""The detail card shown when the tray icon is clicked.

A ``Qt.Popup`` window, so clicking anywhere else dismisses it — the behaviour
people already expect from a tray flyout, and it saves having to manage focus.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFontMetrics, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.compute import TIER_EMOJI
from ..core.i18n import t
from ..core.view import ProviderView
from . import theme
from .elided import ElidedLabel
from .loading_overlay import LoadingOverlay
from .popup import SHADOW_MARGIN, _Meter, _rgba
from .provider_icons import ProviderMark
from .refresh_feedback import RefreshFeedback
from .wrapping import WrappingLabel

PANEL_WIDTH = 340


class DetailPanel(QWidget):
    """Read-only summary of every provider and window."""

    def __init__(self, on_refresh: Callable[[], None]) -> None:
        super().__init__(None)
        self._on_refresh = on_refresh
        self.refresh_feedback = RefreshFeedback(self)
        self.refresh_feedback.changed.connect(self._update_refresh_button)
        self._views: list[ProviderView] = []
        self.recovery = None
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._anchor: QRect | None = None
        self.loading_overlay = LoadingOverlay(self)
        self._rebuild()

    def update_views(self, views: list[ProviderView]) -> None:
        self._views = views
        if self.isVisible():
            self.popup_at(self._anchor)

    def popup_at(self, anchor: QRect | None) -> None:
        """Show near the tray icon, kept inside the screen it belongs to."""
        self._anchor = anchor
        screen = None
        if anchor is not None and not anchor.isNull():
            screen = QGuiApplication.screenAt(anchor.center())
        screen = screen or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)
        self._rebuild()
        self._fit_to_area(area)

        if anchor is not None and not anchor.isNull():
            x = anchor.center().x() - self.width() // 2
            below = anchor.bottom() + 4
            # Put it above the icon when the tray sits at the bottom of the screen.
            y = below if below + self.height() < area.bottom() else anchor.top() - self.height() - 4
        else:
            x = area.right() - self.width()
            y = area.bottom() - self.height()

        x = max(area.left(), min(x, area.right() - self.width()))
        y = max(area.top(), min(y, area.bottom() - self.height()))
        self.move(QPoint(x, y))
        self.show()
        self.raise_()
        self._update_overlay()

    # -- rendering -------------------------------------------------------------

    def _rebuild(self) -> None:
        palette = theme.current()
        _clear_layout(self.layout())
        if self.layout() is None:
            outer = QVBoxLayout(self)
        else:
            outer = self.layout()
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)

        card = QFrame(self)
        card.setObjectName("panel")
        card.setStyleSheet(
            f"""
            QFrame#panel {{
                background-color: {palette.surface.name()};
                border: 1px solid {_rgba(palette.border)};
                border-radius: 14px;
            }}
            QLabel {{ background: transparent; color: {palette.text.name()};
                      font-family: {theme.FONT_STACK}; }}
            QLabel#muted {{ color: {palette.text_muted.name()}; font-size: 12px; }}
            QScrollArea, QWidget#panel-content {{ background: transparent; border: none; }}
            QLabel#title {{ font-size: 13px; font-weight: 700; }}
            QLabel#row {{ font-size: 12px; }}
            QPushButton {{
                background-color: {palette.surface_alt.name()};
                color: {palette.text.name()};
                border: 1px solid {_rgba(palette.border)};
                border-radius: 7px; padding: 5px 12px;
                font-family: {theme.FONT_STACK}; font-size: 12px;
            }}
            """
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 8)
        shadow.setColor(palette.shadow)
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        body = QVBoxLayout(card)
        body.setContentsMargins(16, 14, 16, 14)
        body.setSpacing(10)

        self.scroll = QScrollArea(card)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        self.content = QWidget()
        self.content.setObjectName("panel-content")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.content)
        body.addWidget(self.scroll, 1)

        probe = _muted("", card)
        probe.ensurePolished()
        metrics = QFontMetrics(probe.font())
        self._detail_label_width = max(
            (metrics.horizontalAdvance(item.label)
             for view in self._views for row in view.rows for item in row.details),
            default=0,
        )
        probe.deleteLater()

        if not self._views:
            content_layout.addWidget(_muted(t("status.no_data"), self.content))
        for index, view in enumerate(self._views):
            if index:
                content_layout.addWidget(_separator(self.content, palette))
            content_layout.addLayout(self._provider_block(view, self.content, palette))

        footer = QHBoxLayout()
        self._refresh_status = QLabel(card)
        self._refresh_status.setObjectName("refresh-status")
        footer.addWidget(self._refresh_status)
        footer.addStretch(1)
        refresh = QPushButton(t("menu.refresh"), card)
        refresh.setObjectName("panel-refresh")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_button = refresh
        self._update_refresh_button()
        refresh.clicked.connect(self._refresh_clicked)
        footer.addWidget(refresh)
        body.addLayout(footer)
        self._footer = footer

        self.setFixedWidth(PANEL_WIDTH + SHADOW_MARGIN * 2)

    def _fit_to_area(self, area: QRect) -> None:
        self.ensurePolished()
        # Include the card's one-pixel border on both sides.
        width = PANEL_WIDTH - 34
        layout = self.content.layout()
        natural = layout.totalHeightForWidth(width)
        if natural < 0:
            natural = layout.sizeHint().height()
        if any(view.rows for view in self._views):
            # Nested usage grids need the conservative hint; simple login cards
            # can use their actual wrapped height without a large empty footer gap.
            natural = max(natural, layout.sizeHint().height())
        footer_height = self._footer.sizeHint().height()
        height = natural + footer_height + 10 + 30 + SHADOW_MARGIN * 2
        self.setFixedHeight(min(height, area.height()))
        self.layout().activate()

    def _provider_block(self, view: ProviderView, parent: QWidget, palette) -> QVBoxLayout:
        block = QVBoxLayout()
        block.setSpacing(6)
        block.setAlignment(Qt.AlignmentFlag.AlignTop)

        head = QHBoxLayout()
        head.setSpacing(6)
        mark = ProviderMark(view.provider, parent)
        mark.setObjectName("provider-icon")
        head.addWidget(mark)
        title = ElidedLabel(view.title, parent)
        title.setObjectName("title")
        head.addWidget(title, 1)
        if view.source_status:
            source = QLabel(view.source_status, parent)
            source.setObjectName("muted")
            source.setTextFormat(Qt.TextFormat.PlainText)
            source.setToolTip(view.source_tooltip)
            source.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            source.setProperty("panel-source", True)
            head.addWidget(source)
        block.addLayout(head)

        if view.message:
            from ..core.models import Status

            message = (t("connect.expired_message") if self.recovery is not None
                       and view.status in (Status.EXPIRED, Status.UNAUTHORIZED) else view.message)
            block.addWidget(_muted(message, parent))

        if self.recovery is not None:
            from ..login_recovery import AUTH_REQUIRED

            session = self.recovery.sessions[view.provider]
            if view.status in AUTH_REQUIRED or session.waiting or session.message:
                block.addWidget(_muted(self.recovery.message(view.provider), parent))
                buttons = QHBoxLayout()
                for label, handler in self.recovery.actions(view.provider):
                    button = QPushButton(label, parent)
                    button.setProperty("connection-action", True)
                    button.clicked.connect(lambda _=False, fn=handler: fn())
                    buttons.addWidget(button)
                block.addLayout(buttons)

        for row in view.rows:
            line = QHBoxLayout()
            line.setSpacing(6)
            label = QLabel(f"{TIER_EMOJI[row.tier]} {row.label}", parent)
            label.setObjectName("row")
            line.addWidget(label, 1)
            value = QLabel(row.remaining_text, parent)
            value.setObjectName("row")
            value.setStyleSheet(f"font-weight: 600; color: {row.color};")
            line.addWidget(value)
            block.addLayout(line)

            block.addWidget(_Meter(row.remaining / 100, palette.tier(row.tier), palette.track))

            if row.detail_status:
                block.addWidget(_muted(row.detail_status, parent))
            elif row.details:
                grid = QGridLayout()
                grid.setAlignment(Qt.AlignmentFlag.AlignTop)
                grid.setHorizontalSpacing(8)
                grid.setVerticalSpacing(3)
                grid.setColumnMinimumWidth(0, self._detail_label_width)
                grid.setColumnStretch(1, 1)
                for index, item in enumerate(row.details):
                    label = _muted(item.label, parent)
                    label.setWordWrap(False)
                    label.setProperty("detail-role", "label")
                    value = _muted(item.value, parent)
                    value.setProperty("detail-role", "value")
                    value.setProperty("detail-key", item.key)
                    if item.key == "pace":
                        value.setWordWrap(False)
                    grid.addWidget(label, index, 0, Qt.AlignmentFlag.AlignTop)
                    grid.addWidget(value, index, 1)
                block.addLayout(grid)

        for note in view.notes:
            block.addWidget(_muted(note, parent))
        return block

    def _refresh_clicked(self) -> None:
        if self.refresh_feedback.start():
            self._on_refresh()

    def _update_refresh_button(self) -> None:
        button = self._refresh_button
        feedback = self.refresh_feedback
        button.setText(t("menu.refresh"))
        button.setEnabled(not feedback.busy)
        button.ensurePolished()
        metrics = button.fontMetrics()
        button.setFixedWidth(metrics.horizontalAdvance(t("menu.refresh")) + 28)
        result = feedback.state in ("done", "failed")
        self._refresh_status.setText(feedback.text if result else "")
        color = theme.current().tier("green" if feedback.state == "done" else "orange")
        self._refresh_status.setStyleSheet(f"color: {color.name()}; font-size: 12px;")
        self._update_overlay()

    def _update_overlay(self) -> None:
        self.loading_overlay.setGeometry(self.rect().adjusted(
            SHADOW_MARGIN, SHADOW_MARGIN, -SHADOW_MARGIN, -SHADOW_MARGIN))
        self.loading_overlay.set_busy(self.refresh_feedback.busy)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_overlay()


def _muted(text: str, parent: QWidget) -> QLabel:
    label = WrappingLabel(text, parent)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


def _separator(parent: QWidget, palette) -> QFrame:
    line = QFrame(parent)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background-color: {_rgba(palette.border)}; border: none;")
    return line


def _clear_layout(layout) -> None:
    """Drop every child so the panel can be rebuilt from fresh data."""
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        else:
            _clear_layout(item.layout())
