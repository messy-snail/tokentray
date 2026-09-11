"""Refresh feedback that survives rebuilding the detail panel's widgets."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ..core.i18n import t

MIN_BUSY_MS = 600
RESULT_MS = 1800


class RefreshFeedback(QObject):
    changed = Signal()

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.state = "idle"
        self._started = 0.0
        self._success = False
        self._completion = QTimer(self)
        self._completion.setSingleShot(True)
        self._completion.timeout.connect(self._show_result)
        self._reset = QTimer(self)
        self._reset.setSingleShot(True)
        self._reset.timeout.connect(self._clear)

    @property
    def busy(self) -> bool:
        return self.state == "busy"

    @property
    def text(self) -> str:
        if self.busy:
            return t("refresh.busy")
        if self.state != "idle":
            return t("refresh." + self.state)
        return t("menu.refresh")

    def start(self) -> bool:
        if self.busy:
            return False
        self._reset.stop()
        self._completion.stop()
        self.state = "busy"
        self._started = time.monotonic()
        self.changed.emit()
        return True

    @Slot(bool)
    def finish(self, success: bool) -> None:
        if not self.busy:
            return
        self._success = success
        elapsed = int((time.monotonic() - self._started) * 1000)
        self._completion.start(max(0, MIN_BUSY_MS - elapsed))

    @Slot()
    def _show_result(self) -> None:
        if not self.busy:
            return
        self.state = "done" if self._success else "failed"
        self.changed.emit()
        self._reset.start(RESULT_MS)

    @Slot()
    def _clear(self) -> None:
        self.state = "idle"
        self.changed.emit()
