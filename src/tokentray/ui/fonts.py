"""Bundled Pretendard v1.3.9, registered only for this application."""

# Source: https://github.com/orioncactus/pretendard/tree/v1.3.9/packages/pretendard/dist/public/static
# The upstream OFL license is distributed alongside the unmodified font files.

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

FONT_DIR = Path(__file__).resolve().parent.parent / "resources" / "fonts"


def initialize_fonts(app: QApplication) -> None:
    if not app.property("tokentray-fonts-loaded"):
        for weight in ("Regular", "SemiBold", "Bold"):
            font_id = QFontDatabase.addApplicationFont(str(FONT_DIR / f"Pretendard-{weight}.otf"))
            if font_id < 0:
                logging.getLogger("tokentray").warning("Could not load Pretendard %s", weight)
        app.setProperty("tokentray-fonts-loaded", True)
    font = QFont("Pretendard", 10)
    if sys.platform == "win32":
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
