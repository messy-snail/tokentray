"""A single-line title that preserves its full text in a tooltip."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class ElidedLabel(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        self._full_text = text
        super().__init__(text, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setToolTip(text)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def _refresh(self) -> None:
        self.setText(self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, self.contentsRect().width(),
        ))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._refresh()
