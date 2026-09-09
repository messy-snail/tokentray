"""Tray icon rendering.

The icon has to answer one question at 16 pixels: how much is left, and is that
fine or not. So it is a ring that drains clockwise from the top, coloured by
tier. With two providers it becomes two concentric rings - Claude outside,
Codex inside - rather than two halves of one ring: identity is carried by the
radius, each provider still gets a full turn (1% = 3.6 degrees, not 1.8), and
two providers sitting at the same tier can no longer merge into what looks like
a single unbroken ring.

Ring order follows the caller's list order, which is provider-registry order.
Nothing is sorted here on purpose - the tooltip and the detail panel render the
same list unsorted, and a sort in one of the three would let them disagree.

The reference implementation cycled between separate per-window icons every four
seconds. That animates in the corner of the eye and still only shows one number
at a time; static rings show both at once and never move.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from ..core.compute import TIER_COLORS, tier_for
from ..core.view import ProviderView
from . import theme

# 36/40/44 are 18/20/22pt at 2x: without an exact raster a Retina menu bar
# downsamples the 48px one, which softens the gap between the two rings.
ICON_SIZES = (16, 20, 22, 24, 32, 36, 40, 44, 48, 64)

# Qt measures arc angles in 1/16th of a degree, counter-clockwise from 3 o'clock.
_DEG = 16
_TOP = 90 * _DEG

# Past three rings the innermost one is too short to read at tray sizes, so the
# icon stops there. Nothing is lost outright: the tooltip still lists everyone.
MAX_RINGS = 3

_MARGIN_FRAC = 0.06     # transparent padding outside the outermost stroke
_MIN_MARGIN = 1.0
_GAP_FRAC = 0.055       # clear radius between neighbouring rings
_MIN_GAP = 1.0
_CORE_FRAC = 0.10       # hole kept in the middle, so the innermost reads as a ring
_MIN_STROKE = 1.7       # below this antialiasing eats the ring entirely
_MAX_STROKE_FRAC = 0.17 # the width a lone ring has always had

_MIN_SWEEP = 6 * _DEG   # a provider at 0% still gets a tick, so it is not mistaken
_IDLE_SPAN = 30 * _DEG  # ... for a provider with no data at all


@dataclass(frozen=True)
class Band:
    """One ring: the centreline its arc is stroked along, and the pen width."""

    radius: float
    stroke: float


@lru_cache(maxsize=128)
def ring_bands(size: int, count: int) -> tuple[Band, ...]:
    """Ring geometry for `count` providers at `size` pixels, outermost first.

    Pure arithmetic, so the layout can be checked without a painter. Widths
    shrink as rings are added but stop at `_MIN_STROKE`; the final clamp is what
    keeps them inside the pixmap when even that floor will not fit.

    At `count == 1` this reproduces the original single-ring geometry exactly,
    which is what lets the packaged assets survive the refactor untouched.
    """
    n = max(1, min(count, MAX_RINGS))
    half = size / 2.0
    margin = max(_MIN_MARGIN, size * _MARGIN_FRAC)
    gap = max(_MIN_GAP, size * _GAP_FRAC)

    ideal = (half - margin - size * _CORE_FRAC - gap * (n - 1)) / n
    # Order matters: capping after the floor would let _MAX_STROKE_FRAC win on a
    # tiny pixmap and hand back a stroke thinner than _MIN_STROKE.
    stroke = max(_MIN_STROKE, min(size * _MAX_STROKE_FRAC, ideal))
    stroke = min(stroke, (half - margin - gap * (n - 1)) / n)

    return tuple(
        Band(half - margin - k * (stroke + gap) - stroke / 2.0, stroke)
        for k in range(n)
    )


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
        _paint_rings(painter, size, views)
    finally:
        painter.end()
    return pixmap


def _paint_rings(painter: QPainter, size: int, views: list[ProviderView]) -> None:
    palette = theme.current()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # Every enabled provider keeps a slot whether or not it has data. Dropping
    # the empty ones would shuffle the remaining rings between polls, so the
    # same arc length would mean a different thing each time you glanced at it.
    bands = ring_bands(size, len(views) or 1)

    for index, band in enumerate(bands):
        rect = _band_rect(size, band)
        painter.setPen(_pen(palette.track, band.stroke))
        painter.drawEllipse(rect)

        remaining = views[index].worst_remaining if index < len(views) else None
        if remaining is None:
            continue
        swept = max(_MIN_SWEEP, round(360 * _clamp(remaining) / 100 * _DEG))
        painter.setPen(_pen(QColor(TIER_COLORS[tier_for(remaining)]), band.stroke))
        painter.drawArc(rect, _TOP, -swept)

    if not any(view.worst_remaining is not None for view in views):
        # Nothing configured yet: bare tracks read as "broken", so leave a faint
        # arc on the outer ring to show the app is alive but has no data.
        painter.setPen(_pen(QColor(palette.text_muted), bands[0].stroke))
        painter.drawArc(_band_rect(size, bands[0]), _TOP, -_IDLE_SPAN)


def _band_rect(size: int, band: Band) -> QRectF:
    centre = size / 2.0
    return QRectF(
        centre - band.radius, centre - band.radius, band.radius * 2, band.radius * 2
    )


def _clamp(remaining: float) -> float:
    return max(0.0, min(100.0, float(remaining)))


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    return pen


def render_app_pixmap(size: int) -> QPixmap:
    """The identity mark at one size: two nearly-closed rings at a neutral colour.

    Two rings rather than one so the dock, the installer and the tray read as
    the same mark. Split out from :func:`app_icon` so the packaging script can
    render it at the sizes a .icns or .ico wants, which run far past tray sizes.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        green = QColor(TIER_COLORS["green"])
        for band in ring_bands(size, 2):
            # Both arcs fully opaque: a dimmed inner ring turns muddy where the
            # 16px ICO entry blends it against whatever is behind the icon.
            painter.setPen(_pen(green, band.stroke))
            painter.drawArc(_band_rect(size, band), _TOP, -300 * _DEG)
    finally:
        painter.end()
    return pixmap


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """Window/dock icon: the identity mark at every size.

    Cached because the tray rebuilds it on every notification, and unlike the
    tray icon it takes no colour from the palette - so it cannot go stale when
    the desktop switches between light and dark.
    """
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(render_app_pixmap(size))
    return icon
