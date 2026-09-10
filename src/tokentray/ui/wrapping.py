"""Height-aware labels for vertically scrolling forms."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class WrappingLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_minimum_height()

    def setText(self, text: str) -> None:
        super().setText(text)
        self._update_minimum_height()

    def _update_minimum_height(self) -> None:
        # QLabel includes its minimum height in heightForWidth. Clear the old
        # constraint first so wider windows and shorter text can shrink again.
        self.setMinimumHeight(0)
        self.setMinimumHeight(max(0, self.heightForWidth(self.width())))
