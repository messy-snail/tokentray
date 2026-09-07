"""Render the packaged icon assets from the app's own drawing code.

The tray icon is painted at runtime, but a .app bundle, a .exe and a Linux
desktop entry all need files on disk. Rather than hand-draw a second version of
the mark that would drift from the tray, this renders `ui.icons` at the sizes
each container wants and assembles the containers here - both formats are a
header plus embedded PNGs, so no image library is needed.

Run after changing the mark, and commit the results:

    QT_QPA_PLATFORM=offscreen uv run python packaging/make_icons.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packaging" / "resources"

# Windows stops at 256; macOS wants everything up to 1024. hicolor takes the PNGs.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)

# icns type -> pixel size. Every one of these accepts a PNG payload.
ICNS_TYPES = {
    b"icp4": 16,
    b"icp5": 32,
    b"ic11": 32,
    b"ic12": 64,
    b"ic07": 128,
    b"ic08": 256,
    b"ic13": 256,
    b"ic09": 512,
    b"ic14": 512,
    b"ic10": 1024,
}


def render(size: int) -> bytes:
    """One PNG of the identity mark, straight from the runtime painter."""
    from PySide6.QtCore import QBuffer, QByteArray

    from tokentray.ui import icons

    # Keep the QByteArray alive: QBuffer only borrows it, and a temporary would
    # be collected out from under the C++ side.
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    icons.render_app_pixmap(size).save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def write_ico(pngs: dict[int, bytes], path: Path) -> None:
    """ICONDIR + one ICONDIRENTRY per size, with PNG payloads (Vista and later)."""
    entries, blobs = b"", b""
    offset = 6 + 16 * len(pngs)
    for size in sorted(pngs):
        data = pngs[size]
        # 0 in the size byte means 256: the field is a single unsigned byte.
        entries += struct.pack(
            "<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset
        )
        blobs += data
        offset += len(data)
    path.write_bytes(struct.pack("<HHH", 0, 1, len(pngs)) + entries + blobs)


def write_icns(pngs: dict[int, bytes], path: Path) -> None:
    """'icns' magic, total length, then one typed chunk per representation."""
    chunks = b""
    for icns_type, size in ICNS_TYPES.items():
        data = pngs[size]
        chunks += icns_type + struct.pack(">I", len(data) + 8) + data
    path.write_bytes(b"icns" + struct.pack(">I", len(chunks) + 8) + chunks)


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    OUT.mkdir(parents=True, exist_ok=True)

    # QPixmap needs a QGuiApplication even under the offscreen plugin.
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])

    wanted = sorted(set(ICO_SIZES) | set(PNG_SIZES) | set(ICNS_TYPES.values()))
    pngs = {size: render(size) for size in wanted}

    for size in PNG_SIZES:
        (OUT / f"tokentray-{size}.png").write_bytes(pngs[size])
    write_ico({size: pngs[size] for size in ICO_SIZES}, OUT / "tokentray.ico")
    write_icns(pngs, OUT / "tokentray.icns")

    for file in sorted(OUT.iterdir()):
        print(f"  {file.name:24} {file.stat().st_size:>8,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
