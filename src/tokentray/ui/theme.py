"""Colour palette, resolved once per theme change.

Qt reports the desktop's light/dark preference through the application palette,
so we derive from that rather than probing each OS separately. Every widget
takes its colours from a Palette instance, which keeps the dark variant from
drifting out of sync with the light one.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from ..core.compute import TIER_COLORS


@dataclass(frozen=True)
class Palette:
    dark: bool
    surface: QColor          # toast / panel background
    surface_alt: QColor      # inset rows
    text: QColor
    text_muted: QColor
    border: QColor
    track: QColor            # unfilled part of a progress bar or ring
    shadow: QColor

    def tier(self, name: str) -> QColor:
        return QColor(TIER_COLORS.get(name, TIER_COLORS["green"]))


LIGHT = Palette(
    dark=False,
    surface=QColor(252, 252, 253),
    surface_alt=QColor(242, 243, 245),
    text=QColor(24, 26, 30),
    text_muted=QColor(110, 116, 126),
    border=QColor(0, 0, 0, 28),
    track=QColor(0, 0, 0, 38),
    shadow=QColor(0, 0, 0, 90),
)

DARK = Palette(
    dark=True,
    surface=QColor(32, 34, 38),
    surface_alt=QColor(44, 47, 52),
    text=QColor(238, 240, 243),
    text_muted=QColor(150, 156, 166),
    border=QColor(255, 255, 255, 30),
    track=QColor(255, 255, 255, 34),
    shadow=QColor(0, 0, 0, 160),
)


def is_dark() -> bool:
    """True when the desktop is using a dark theme.

    Falls back to light when there is no application yet (offscreen tests, the
    CLI), which is the safer default: light text on a light card is unreadable,
    dark-on-dark merely looks flat.
    """
    app = QApplication.instance()
    if app is None:
        return False
    window = app.palette().color(QPalette.ColorRole.Window)
    return window.lightness() < 128


def current() -> Palette:
    return DARK if is_dark() else LIGHT


FONT_STACK = '"Segoe UI Variable", "Segoe UI", -apple-system, "SF Pro Text", ' \
             'Inter, "Noto Sans KR", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif'
MONO_STACK = '"Cascadia Mono", Consolas, "SF Mono", "JetBrains Mono", monospace'
