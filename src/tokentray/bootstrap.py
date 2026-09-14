"""Decisions that have to be made before, or independently of, the Controller.

Each of these runs at most once per process and none of them needs the running
application, which is why they sit outside it: the choice of Qt platform plugin
has to happen before QApplication exists at all, and logging has to be working
before anything it might record.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import sys

from PySide6.QtCore import QLocale, QUrl
from PySide6.QtGui import QDesktopServices

from .core import i18n, paths
from .core.config import Config


def initial_language(config: Config) -> str:
    """Use the configured language, falling back to the desktop locale once.

    Only on first run: after that an explicit choice, including a deliberate
    switch back to English, has to survive.
    """
    explicit = config.get("language")
    if isinstance(explicit, str) and explicit and paths.config_file().exists():
        return explicit

    detected = i18n.normalize(QLocale.system().name())
    config.set("language", detected)
    try:
        config.save()
    except OSError:
        pass
    return detected


def select_platform_plugin(config: Config) -> None:
    """Prefer XWayland on Wayland sessions.

    Wayland gives clients no say in window placement, so toasts land wherever
    the compositor wants and the tray icon reports no geometry to anchor to.
    Running through XWayland restores both. Overridable for anyone who would
    rather have native Wayland than positioned popups.
    """
    if not sys.platform.startswith("linux"):
        return
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if not config.get("linux.force_xwayland", True):
        return
    if os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def open_tray_settings() -> None:
    QDesktopServices.openUrl(QUrl("ms-settings:taskbar"))


def configure_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        paths.log_file(), maxBytes=512_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger("tokentray")
    root.setLevel(logging.INFO)
    root.handlers = [handler]
    from . import __version__

    root.info(
        "startup version=%s platform=%s python=%s standalone=%s",
        __version__, sys.platform, platform.python_version(), bool(getattr(sys, "frozen", False)),
    )
