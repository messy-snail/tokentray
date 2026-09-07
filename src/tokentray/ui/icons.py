"""Tray icon rendering.

The icon has to answer one question at 16 pixels: how much is left, and is that
fine or not. So it is a ring that drains from the top, coloured by tier — the
left half for Claude, the right half for Codex, one full ring when only one
provider is configured.

The reference implementation cycled between separate per-window icons every four
seconds. That animates in the corner of the eye and still only shows one number
at a time; a static split ring shows both at once and never moves.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from ..core.compute import TIER_COLORS, tier_for
from ..core.view import ProviderView
from . import theme

ICON_SIZES = (16, 20, 22, 24, 32, 48, 64)

# Qt measures arc angles in 1/16th of a degree, counter-clockwise from 3 o'clock.
_DEG = 16
_TOP = 90 * _DEG


def build_icon(views: list[ProviderView] | None = None) -> QIcon:
    """A multi-resolution icon so Windows, macOS and GNOME each pick a crisp size."""
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(render_pixmap(views or [], size))
    return icon


def render_pixmap(views: list[ProviderView], size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _paint_ring(painter, size, [v for v in views if v.worst_remaining is not None])
    finally:
        painter.end()
    return pixmap


def _paint_ring(painter: QPainter, size: int, views: list[ProviderView]) -> None:
    palette = theme.current()
    # Thin rings vanish at 16px and look weak at 64; scale with a floor.
    thickness = max(2.0, size * 0.17)
    inset = thickness / 2 + max(1.0, size * 0.06)
    rect = QRectF(inset, inset, size - inset * 2, size - inset * 2)

    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_pen(palette.track, thickness))
    painter.drawEllipse(rect)

    if not views:
        # Nothing configured yet: an empty track alone reads as "broken", so
        # leave a faint full ring to show the app is alive but has no data.
        painter.setPen(_pen(QColor(palette.text_muted), thickness))
        painter.drawArc(rect, _TOP, -30 * _DEG)
        return

    if len(views) == 1:
        _draw_segment(painter, rect, thickness, views[0], span=360, clockwise=True)
        return

    # Two providers: Claude drains down the left, Codex down the right, both
    # starting from 12 o'clock so they are read the same way.
    ordered = sorted(views, key=lambda v: 0 if v.provider == "claude" else 1)
    _draw_segment(painter, rect, thickness, ordered[0], span=180, clockwise=False)
    _draw_segment(painter, rect, thickness, ordered[1], span=180, clockwise=True)


def _draw_segment(
    painter: QPainter,
    rect: QRectF,
    thickness: float,
    view: ProviderView,
    *,
    span: int,
    clockwise: bool,
) -> None:
    remaining = view.worst_remaining
    if remaining is None:
        return
    swept = int(span * max(0, min(100, remaining)) / 100 * _DEG)
    if swept <= 0:
        return
    painter.setPen(_pen(QColor(TIER_COLORS[tier_for(remaining)]), thickness))
    painter.drawArc(rect, _TOP, -swept if clockwise else swept)


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    return pen


def render_app_pixmap(size: int) -> QPixmap:
    """The identity mark at one size: a nearly-closed ring at a neutral colour.

    Split out from :func:`app_icon` so the packaging script can render the same
    mark at the sizes a .icns or .ico wants, which run far past the tray sizes.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        thickness = max(2.0, size * 0.17)
        inset = thickness / 2 + max(1.0, size * 0.06)
        rect = QRectF(inset, inset, size - inset * 2, size - inset * 2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(_pen(QColor(TIER_COLORS["green"]), thickness))
        painter.drawArc(rect, _TOP, -300 * _DEG)
    finally:
        painter.end()
    return pixmap


def app_icon() -> QIcon:
    """Window/dock icon: a full ring at a neutral colour."""
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(render_app_pixmap(size))
    return icon
