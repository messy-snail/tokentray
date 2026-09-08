"""Toast notifications drawn by us rather than by the OS.

Native notifications are the obvious choice and the wrong one here: macOS only
delivers them from a signed bundle, Windows needs a registered AppUserModelID
and silently swallows the legacy balloon path under Focus Assist, and the three
platforms disagree about styling. A window we draw ourselves looks the same
everywhere, always appears, and can show a progress meter — which is most of
what the message is.

The OS notification centre is still used as a secondary channel; see
``notify.dispatcher``.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.alerts import AlertEvent
from ..notify.formatting import summarize
from . import icons, theme

CARD_WIDTH = 372
SHADOW_MARGIN = 20
GAP = 10
EDGE_MARGIN = 16
MAX_VISIBLE = 3


class _Meter(QWidget):
    """Slim rounded progress bar. A number plus a bar reads faster than either."""

    def __init__(self, fraction: float, color: QColor, track: QColor) -> None:
        super().__init__()
        self._fraction = max(0.0, min(1.0, fraction))
        self._color = color
        self._track = track
        self.setFixedHeight(6)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        radius = self.height() / 2

        painter.setBrush(self._track)
        painter.drawRoundedRect(self.rect(), radius, radius)

        filled = int(self.width() * self._fraction)
        if filled >= 2:
            painter.setBrush(self._color)
            painter.drawRoundedRect(QRect(0, 0, filled, self.height()), radius, radius)
        painter.end()


class Toast(QWidget):
    """One notification card.

    Positioning is done by the manager; this widget only knows how to look right
    and when to fade itself out.
    """

    closed = Signal(object)
    activated = Signal()

    def __init__(
        self,
        *,
        title: str,
        body: str,
        tier: str = "orange",
        fraction: float | None = None,
        detail: str = "",
        duration: int = 8,
        sticky: bool = False,
        actions: list[tuple[str, Callable[[], None]]] | None = None,
    ) -> None:
        super().__init__(None)
        self._palette = theme.current()
        self._sticky = sticky

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Without this the toast steals focus from whatever the user is typing in.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._build(title, body, tier, fraction, detail, actions or [])

        self._dismiss = QTimer(self)
        self._dismiss.setSingleShot(True)
        self._dismiss.timeout.connect(self.dismiss)
        self._duration_ms = max(2, duration) * 1000

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._slide = QPropertyAnimation(self, b"pos", self)

    # -- construction ----------------------------------------------------------

    def _build(
        self,
        title: str,
        body: str,
        tier: str,
        fraction: float | None,
        detail: str,
        actions: list[tuple[str, Callable[[], None]]],
    ) -> None:
        palette = self._palette
        accent = palette.tier(tier)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)

        card = QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(
            f"""
            QFrame#card {{
                background-color: {palette.surface.name()};
                border: 1px solid {_rgba(palette.border)};
                border-radius: 14px;
            }}
            QLabel {{ background: transparent; color: {palette.text.name()}; }}
            QLabel#muted {{ color: {palette.text_muted.name()}; }}
            QPushButton {{
                background-color: {palette.surface_alt.name()};
                color: {palette.text.name()};
                border: 1px solid {_rgba(palette.border)};
                border-radius: 7px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{ background-color: {_rgba(accent, 40)}; }}
            QPushButton#close {{
                background: transparent; border: none;
                color: {palette.text_muted.name()};
                padding: 0px; font-size: 15px;
            }}
            QPushButton#close:hover {{ color: {palette.text.name()}; }}
            """
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(palette.shadow)
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        row = QHBoxLayout(card)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        stripe = QFrame(card)
        stripe.setFixedWidth(4)
        stripe.setStyleSheet(
            f"background-color: {accent.name()};"
            "border-top-left-radius: 13px; border-bottom-left-radius: 13px;"
        )
        row.addWidget(stripe)

        content = QVBoxLayout()
        content.setContentsMargins(14, 12, 12, 13)
        content.setSpacing(7)
        row.addLayout(content, 1)

        header = QHBoxLayout()
        header.setSpacing(8)
        mark = QLabel(card)
        mark.setObjectName("app-icon")
        mark.setFixedSize(16, 16)
        mark.setPixmap(icons.render_app_pixmap(16))
        header.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        heading = QLabel(title, card)
        heading.setStyleSheet(
            f"font-family: {theme.FONT_STACK}; font-size: 11px; font-weight: 600;"
            f" color: {palette.text_muted.name()}; letter-spacing: 0.4px;"
        )
        header.addWidget(heading, 1)

        close = QPushButton("×", card)
        close.setObjectName("close")
        close.setFixedSize(18, 18)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.dismiss)
        header.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        content.addLayout(header)

        message = QLabel(body, card)
        message.setWordWrap(True)
        message.setStyleSheet(
            f"font-family: {theme.FONT_STACK}; font-size: 14px; font-weight: 600;"
        )
        content.addWidget(message)

        if fraction is not None:
            content.addWidget(_Meter(fraction, accent, palette.track))

        if detail:
            sub = QLabel(detail, card)
            sub.setObjectName("muted")
            sub.setWordWrap(True)
            sub.setStyleSheet(
                f"font-family: {theme.FONT_STACK}; font-size: 12px;"
                f" color: {palette.text_muted.name()};"
            )
            content.addWidget(sub)

        if actions:
            buttons = QHBoxLayout()
            buttons.setSpacing(8)
            buttons.addStretch(1)
            for label, handler in actions:
                button = QPushButton(label, card)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setStyleSheet(f"font-family: {theme.FONT_STACK}; font-size: 12px;")
                button.clicked.connect(lambda _=False, fn=handler: (fn(), self.dismiss()))
                buttons.addWidget(button)
            content.addLayout(buttons)

        self.setFixedWidth(CARD_WIDTH + SHADOW_MARGIN * 2)
        self.adjustSize()

    # -- behaviour -------------------------------------------------------------

    def present(self, target: QPoint, *, slide_from: int) -> None:
        """Fade and slide into ``target``. ``slide_from`` is a signed x offset."""
        self.setWindowOpacity(0.0)
        self.move(target + QPoint(slide_from, 0))
        self.show()

        self._slide.stop()
        self._slide.setDuration(220)
        self._slide.setStartValue(self.pos())
        self._slide.setEndValue(target)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.start()

        self._animate_opacity(1.0, 180)
        if not self._sticky:
            self._dismiss.start(self._duration_ms)

    def glide_to(self, target: QPoint) -> None:
        """Move to a new slot after a toast below this one was dismissed."""
        self._slide.stop()
        self._slide.setDuration(160)
        self._slide.setStartValue(self.pos())
        self._slide.setEndValue(target)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.start()

    def dismiss(self) -> None:
        self._dismiss.stop()
        self._fade.finished.connect(self.close)
        self._animate_opacity(0.0, 160)

    def _animate_opacity(self, value: float, ms: int) -> None:
        self._fade.stop()
        self._fade.setDuration(ms)
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(value)
        self._fade.start()

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt naming
        # Reading a toast should not race a countdown.
        self._dismiss.stop()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt naming
        if not self._sticky:
            self._dismiss.start(self._duration_ms)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
            self.dismiss()
        super().mouseReleaseEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.closed.emit(self)
        super().closeEvent(event)


class ToastManager:
    """Owns the on-screen stack: placement, ordering and overflow."""

    def __init__(self, *, duration: int = 8, anchor_widget_geometry: Callable[[], QRect | None] | None = None) -> None:
        self.duration = duration
        self._toasts: list[Toast] = []
        self._anchor = anchor_widget_geometry
        self.on_activated: Callable[[], None] | None = None

    def show_alerts(self, events: list[AlertEvent]) -> None:
        """Display ``events``, collapsing a burst into a single summary card.

        Four windows crossing a threshold in the same poll is one situation, not
        four notifications; stacking them all would bury the screen.
        """
        if not events:
            return
        if len(events) > MAX_VISIBLE:
            worst = min(events, key=lambda e: e.row.remaining if e.row else 100)
            summary = summarize(events)
            self.show(
                Toast(
                    title=summary.title,
                    body=summary.body,
                    tier=worst.tier,
                    detail=summary.detail,
                    duration=self.duration,
                )
            )
            return
        for event in events:
            row = event.row
            self.show(
                Toast(
                    title=event.title,
                    body=event.body,
                    tier=event.tier,
                    fraction=(row.remaining / 100) if row else None,
                    detail=_detail_for(event),
                    duration=self.duration,
                )
            )

    def show(self, toast: Toast) -> None:
        toast.closed.connect(self._forget)
        if self.on_activated is not None:
            toast.activated.connect(self.on_activated)
        self._toasts.append(toast)
        area, from_top = self._area()
        toast.present(
            self._slot(len(self._toasts) - 1, toast, area, from_top),
            slide_from=max(24, toast.width() // 6),
        )

    def clear(self) -> None:
        for toast in list(self._toasts):
            toast.dismiss()

    # -- placement -------------------------------------------------------------

    def _area(self) -> tuple[QRect, bool]:
        """Available screen rect, and whether to stack downward from the top.

        macOS puts its menu bar and notifications at the top of the screen, so a
        toast belongs there; Windows and Linux put the tray at the bottom.
        """
        import sys

        rect: QRect | None = None
        if self._anchor is not None:
            anchor = self._anchor()
            if anchor is not None and not anchor.isNull():
                screen = QGuiApplication.screenAt(anchor.center())
                if screen is not None:
                    rect = screen.availableGeometry()
        if rect is None:
            screen = QGuiApplication.primaryScreen()
            rect = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)
        return rect, sys.platform == "darwin"

    def _slot(self, index: int, toast: Toast, area: QRect, from_top: bool) -> QPoint:
        x = area.right() - toast.width() + SHADOW_MARGIN - EDGE_MARGIN
        offset = sum(t.height() - SHADOW_MARGIN + GAP for t in self._toasts[:index])
        if from_top:
            y = area.top() - SHADOW_MARGIN + EDGE_MARGIN + offset
        else:
            y = area.bottom() - toast.height() + SHADOW_MARGIN - EDGE_MARGIN - offset
        return QPoint(x, y)

    def _forget(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        area, from_top = self._area()
        for index, remaining in enumerate(self._toasts):
            remaining.glide_to(self._slot(index, remaining, area, from_top))


def _detail_for(event: AlertEvent) -> str:
    row = event.row
    if row is None:
        return ""
    parts = [part for part in (row.refills, row.pace) if part]
    if row.pace_icon:
        parts = parts[:-1] + [f"{parts[-1]} {row.pace_icon}"] if parts else parts
    return " · ".join(parts)


def _rgba(color: QColor, alpha: int | None = None) -> str:
    value = QColor(color)
    if alpha is not None:
        value.setAlpha(alpha)
    return f"rgba({value.red()}, {value.green()}, {value.blue()}, {value.alpha() / 255:.3f})"
