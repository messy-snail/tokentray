"""A card-local busy overlay, without native windows or graphics effects."""

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..core.i18n import t
from . import theme


class LoadingOverlay(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("panel-loading")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._advance)
        self.hide()

    def set_busy(self, busy: bool) -> None:
        if busy:
            self.show()
            self.raise_()
        else:
            self.hide()

    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _advance(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, event) -> None:
        palette = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        veil = QColor(palette.surface)
        veil.setAlpha(225)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(veil)
        painter.drawRoundedRect(QRectF(self.rect()), 14, 14)
        ring = QRectF(self.width() / 2 - 16, self.height() / 2 - 28, 32, 32)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(palette.track, 3))
        painter.drawEllipse(ring)
        painter.setPen(QPen(palette.tier("green"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(ring, -self._angle * 16, 100 * 16)
        painter.setPen(palette.text)
        painter.drawText(QRectF(8, ring.bottom() + 8, self.width() - 16, 20),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         t("refresh.busy") + "…")

    def mousePressEvent(self, event) -> None:
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        event.accept()

    def wheelEvent(self, event) -> None:
        event.accept()
