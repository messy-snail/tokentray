"""System tray icon and menu.

The tray presence is the whole point of the app being invisible otherwise: it is
how the user knows something is running on their behalf. So a missing tray host
is treated as a condition to retry and then report, never as a reason to exit
quietly.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QRect, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..core import i18n
from ..core.i18n import t
from ..core.view import ProviderView, tooltip
from . import icons

# GNOME and KDE can start their tray host after the session's autostart entries,
# so an early "no tray" answer is often just a race.
RETRY_INTERVAL_MS = 5_000
MAX_RETRIES = 12


class Tray(QObject):
    open_panel = Signal()
    refresh_requested = Signal()
    test_requested = Signal()
    pause_toggled = Signal()
    autostart_toggled = Signal(bool)
    language_selected = Signal(str)
    open_log_requested = Signal()
    quit_requested = Signal()
    unavailable = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._icon = QSystemTrayIcon()
        self._icon.setIcon(icons.build_icon())
        self._icon.setToolTip("tokentray")
        self._paused = False
        self._retries = 0
        self._menu: QMenu | None = None
        self._build_menu()

        if sys.platform != "darwin":
            # macOS routes every click to the context menu, so there is no
            # separate left-click to bind; elsewhere it opens the detail panel.
            self._icon.activated.connect(self._on_activated)

    # -- lifecycle -------------------------------------------------------------

    def start(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._icon.show()
            return
        self._retries += 1
        if self._retries > MAX_RETRIES:
            self.unavailable.emit()
            return
        QTimer.singleShot(RETRY_INTERVAL_MS, self.start)

    def stop(self) -> None:
        self._icon.hide()

    @property
    def available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def geometry(self) -> QRect | None:
        """Where the icon sits, for anchoring the panel and toasts.

        Returns None on desktops that refuse to say (most Wayland compositors).
        """
        rect = self._icon.geometry()
        return None if rect.isNull() or rect.isEmpty() else rect

    # -- updates ---------------------------------------------------------------

    def update_views(self, views: list[ProviderView]) -> None:
        self._icon.setIcon(icons.build_icon(views))
        self._icon.setToolTip(tooltip(views))

    def show_message(self, title: str, body: str) -> None:
        """Secondary delivery through the OS notification centre.

        Best effort by design: it is suppressed by Focus Assist on Windows and
        needs a signed bundle on macOS, which is exactly why the custom toast is
        the primary channel rather than this.
        """
        try:
            self._icon.showMessage(title, body, icons.app_icon(), 6000)
        except Exception:
            pass

    def set_autostart_checked(self, enabled: bool) -> None:
        self._autostart_action.blockSignals(True)
        self._autostart_action.setChecked(enabled)
        self._autostart_action.blockSignals(False)

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._pause_action.setText(t("menu.resume_alerts") if paused else t("menu.pause_alerts"))

    def retranslate(self) -> None:
        """Rebuild the menu after a language change."""
        self._build_menu()

    # -- internals -------------------------------------------------------------

    def _build_menu(self) -> None:
        menu = QMenu()

        open_action = QAction(t("menu.open_panel"), menu)
        open_action.triggered.connect(self.open_panel.emit)
        menu.addAction(open_action)

        refresh = QAction(t("menu.refresh"), menu)
        refresh.triggered.connect(self.refresh_requested.emit)
        menu.addAction(refresh)

        menu.addSeparator()

        self._pause_action = QAction(
            t("menu.resume_alerts") if self._paused else t("menu.pause_alerts"), menu
        )
        self._pause_action.triggered.connect(self.pause_toggled.emit)
        menu.addAction(self._pause_action)

        test = QAction(t("menu.test_alert"), menu)
        test.triggered.connect(self.test_requested.emit)
        menu.addAction(test)

        menu.addSeparator()

        language_menu = menu.addMenu(t("menu.language"))
        group = QActionGroup(language_menu)
        group.setExclusive(True)
        for code, name in i18n.available_languages():
            action = QAction(name, language_menu)
            action.setCheckable(True)
            action.setChecked(code == i18n.current_language())
            action.triggered.connect(lambda _=False, c=code: self.language_selected.emit(c))
            group.addAction(action)
            language_menu.addAction(action)

        self._autostart_action = QAction(t("menu.autostart"), menu)
        self._autostart_action.setCheckable(True)
        self._autostart_action.toggled.connect(self.autostart_toggled.emit)
        menu.addAction(self._autostart_action)

        log = QAction(t("menu.open_log"), menu)
        log.triggered.connect(self.open_log_requested.emit)
        menu.addAction(log)

        menu.addSeparator()

        quit_action = QAction(t("menu.quit"), menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        # Keep a reference: QSystemTrayIcon does not take ownership, and a
        # garbage-collected menu leaves an icon that does nothing on right-click.
        self._menu = menu
        self._icon.setContextMenu(menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.open_panel.emit()
