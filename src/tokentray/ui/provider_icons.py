"""Local service symbols rendered at the target screen's pixel density."""

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QWidget

from ..core.view import PROVIDER_NAMES
from . import icons, theme

RESOURCE_DIR = Path(__file__).resolve().parent.parent / "resources" / "providers"


@lru_cache(maxsize=64)
def provider_pixmap(provider: str | None, size: int, dpr: float, dark: bool) -> QPixmap:
    pixels = max(1, round(size * dpr))
    name = {
        "claude": "claude.svg",
        "codex": f"OpenAI-{'white' if dark else 'black'}-monoblossom.svg",
    }.get(provider)
    if name:
        renderer = QSvgRenderer(str(RESOURCE_DIR / name))
        if renderer.isValid():
            pixmap = QPixmap(pixels, pixels)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            if provider == "claude":
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                painter.fillRect(pixmap.rect(), QColor("#D97757"))
            painter.end()
            pixmap.setDevicePixelRatio(dpr)
            return pixmap
    pixmap = QPixmap(icons.render_app_pixmap(pixels))
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


class ProviderMark(QLabel):
    def __init__(self, provider: str | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.provider = provider
        self.setFixedSize(16, 16)
        self.setAccessibleName(PROVIDER_NAMES.get(provider, "tokentray"))
        self._refresh()

    def _refresh(self) -> None:
        self.setPixmap(provider_pixmap(self.provider, 16, self.devicePixelRatioF(), theme.is_dark()))

    def event(self, event: QEvent) -> bool:
        result = super().event(event)
        if hasattr(self, "provider") and event.type() in (
            QEvent.Type.Show, QEvent.Type.DevicePixelRatioChange, QEvent.Type.PaletteChange,
        ):
            self._refresh()
        return result
