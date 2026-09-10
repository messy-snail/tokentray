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
from .popup import SHADOW_MARGIN, _Meter, _rgba
from .wrapping import WrappingLabel

PANEL_WIDTH = 340


class DetailPanel(QWidget):
    """Read-only summary of every provider and window."""

    def __init__(self, on_refresh: Callable[[], None]) -> None:
        super().__init__(None)
        self._on_refresh = on_refresh
        self._views: list[ProviderView] = []
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._anchor: QRect | None = None
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
        footer.addStretch(1)
        refresh = QPushButton(t("menu.refresh"), card)
        refresh.setObjectName("panel-refresh")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
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
        natural = max(layout.totalHeightForWidth(width), layout.sizeHint().height())
        footer_height = self._footer.sizeHint().height()
        height = natural + footer_height + 10 + 30 + SHADOW_MARGIN * 2
        self.setFixedHeight(min(height, area.height()))
        self.layout().activate()

    def _provider_block(self, view: ProviderView, parent: QWidget, palette) -> QVBoxLayout:
        block = QVBoxLayout()
        block.setSpacing(6)
        block.setAlignment(Qt.AlignmentFlag.AlignTop)

        head = QHBoxLayout()
        title = QLabel(view.title, parent)
        title.setObjectName("title")
        head.addWidget(title, 1)
        if view.source:
            source = _muted(view.source, parent)
            source.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            source.setProperty("panel-source", True)
            head.addWidget(source)
        block.addLayout(head)

        if view.message:
            block.addWidget(_muted(view.message, parent))

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
        self.hide()
        self._on_refresh()


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
