"""Application bootstrap and wiring.

Threading rule for this file: the poller thread produces Snapshots and nothing
else. Every widget touch happens on the main thread, reached only through a
queued signal. Network calls and keyring reads both block — the first for
seconds on a bad connection, the second indefinitely on a Linux SecretService
prompt — so neither may ever run where the UI lives.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

from PySide6.QtCore import (
    QLocale,
    QMetaObject,
    QObject,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from . import autostart, ipc
from .core import i18n, paths
from .core.alerts import AlertState, evaluate
from .core.cache import Cache
from .core.config import Config
from .core.view import ProviderView, build_view

log = logging.getLogger("tokentray")


def main(autostart_launch: bool = False, **kwargs: Any) -> int:
    """Entry point for both ``tokentray`` and ``tokentray-gui``."""
    if "autostart" in kwargs:
        autostart_launch = bool(kwargs["autostart"])
    if "--autostart" in sys.argv:
        autostart_launch = True

    config = Config.load()
    _configure_logging()
    _select_platform_plugin(config)

    from .ui import icons

    QApplication.setApplicationName("tokentray")
    QApplication.setApplicationDisplayName("tokentray")
    QApplication.setDesktopFileName(autostart.APP_ID)
    app = QApplication(sys.argv)
    app.setWindowIcon(icons.app_icon())
    # Closing the detail panel must not end the process; the tray icon is the app.
    app.setQuitOnLastWindowClosed(False)

    controller = Controller(app, config, autostart_launch=autostart_launch)
    if not controller.start():
        # Another instance owns the tray; it has been asked to show itself.
        return 0
    return app.exec()


class PollWorker(QObject):
    """Fetches every provider, one poll at a time, off the UI thread."""

    snapshots_ready = Signal(list)
    requested = Signal(bool)

    def __init__(self, config: Config) -> None:
        super().__init__()
        from .providers import build_providers

        self._providers = build_providers(config, Cache())
        self._busy = False
        self._pending: bool | None = None
        self.requested.connect(self._run)

    @Slot(bool)
    def _run(self, force: bool) -> None:
        # A slow network must not queue polls behind each other: keep at most one
        # pending request and collapse any others into it.
        if self._busy:
            self._pending = force or bool(self._pending)
            return
        self._busy = True
        try:
            while True:
                snapshots = [p.fetch(force=force) for p in self._providers]
                self.snapshots_ready.emit(snapshots)
                if self._pending is None:
                    return
                force, self._pending = self._pending, None
        except Exception:
            log.exception("poll failed")
        finally:
            self._busy = False

    @Slot()
    def shutdown(self) -> None:
        for provider in self._providers:
            provider.close()


class Controller:
    """Owns application state and connects the pieces."""

    def __init__(self, app, config: Config, *, autostart_launch: bool = False) -> None:
        self.app = app
        self.config = config
        self.autostart_launch = autostart_launch
        self.views: list[ProviderView] = []

        self._state = _load_state()
        self.alerts = AlertState.from_dict(self._state.get("alerts"))

        i18n.set_language(_initial_language(config))

        from .notify.dispatcher import Dispatcher
        from .notify.webhook import Webhook
        from .ui.panel import DetailPanel
        from .ui.popup import ToastManager
        from .ui.tray import Tray

        self.tray = Tray()
        self.panel = DetailPanel(on_refresh=lambda: self.refresh(force=True))
        self.toasts = ToastManager(
            duration=config.popup_duration, anchor_widget_geometry=self.tray.geometry
        )
        self.toasts.on_activated = self.show_panel
        self.dispatcher = Dispatcher(
            self.toasts,
            Webhook.from_config(config),
            native=self.tray.show_message,
            native_enabled=bool(config.get("native_notifications", True)),
        )

        self._thread = QThread()
        self._worker = PollWorker(config)
        self._worker.moveToThread(self._thread)
        self._worker.snapshots_ready.connect(self._on_snapshots)

        self._timer = QTimer(self.app)
        self._timer.setInterval(config.poll_interval * 1000)
        self._timer.timeout.connect(lambda: self.refresh(force=False))

        self._instance = ipc.SingleInstance(self._handle_command)
        self._connect_tray()

    # -- lifecycle -------------------------------------------------------------

    def start(self) -> bool:
        if not self._instance.acquire():
            ipc.send_command(ipc.CMD_SHOW)
            return False

        autostart.repair()
        self.tray.set_autostart_checked(autostart.is_enabled())
        self.tray.set_paused(self.alerts.is_paused(time.time()))
        self.tray.unavailable.connect(self._on_tray_unavailable)
        self.tray.start()

        self._thread.start()
        self._timer.start()
        self.refresh(force=False)

        if not self.autostart_launch and not self._state.get("welcomed"):
            self._show_welcome()
        self.app.aboutToQuit.connect(self._shutdown)
        return True

    def _shutdown(self) -> None:
        self._timer.stop()
        self.toasts.clear()
        self.tray.stop()
        # Close the HTTP clients on the thread that created them, then join.
        QMetaObject.invokeMethod(
            self._worker, "shutdown", Qt.ConnectionType.BlockingQueuedConnection
        )
        self._thread.quit()
        self._thread.wait(3000)
        self._instance.release()
        self._save_state()

    def quit(self) -> None:
        self.app.quit()

    # -- polling ---------------------------------------------------------------

    def refresh(self, *, force: bool) -> None:
        self._worker.requested.emit(force)

    def _on_snapshots(self, snapshots: list) -> None:
        now = datetime.now(timezone.utc)
        self.views = [build_view(snapshot, now) for snapshot in snapshots]
        self.tray.update_views(self.views)
        self.panel.update_views(self.views)

        events = evaluate(
            self.views,
            thresholds=self.config.thresholds,
            remind_before=self.config.remind_before,
            state=self.alerts,
            now=time.time(),
            clock=now,
        )
        self.dispatcher.emit(events)
        self._save_state()

    # -- tray actions ----------------------------------------------------------

    def _connect_tray(self) -> None:
        self.tray.open_panel.connect(self.show_panel)
        self.tray.refresh_requested.connect(lambda: self.refresh(force=True))
        self.tray.test_requested.connect(self.show_test_alert)
        self.tray.pause_toggled.connect(self.toggle_pause)
        self.tray.autostart_toggled.connect(self._set_autostart)
        self.tray.language_selected.connect(self.set_language)
        self.tray.open_log_requested.connect(self._open_log)
        self.tray.quit_requested.connect(self.quit)

    def show_panel(self) -> None:
        self.panel.update_views(self.views)
        self.panel.popup_at(self.tray.geometry())

    def show_test_alert(self) -> None:
        from .ui.popup import Toast

        self.toasts.show(
            Toast(
                title=i18n.t("notify.info_title"),
                body=i18n.t("test.body"),
                tier="green",
                fraction=0.62,
                detail=i18n.t("fmt.refills", dur="3h 42m"),
                duration=self.config.popup_duration,
            )
        )

    def toggle_pause(self) -> None:
        now = time.time()
        if self.alerts.is_paused(now):
            self.alerts.paused_until = 0.0
        else:
            self.alerts.paused_until = now + 3600
        self.tray.set_paused(self.alerts.is_paused(now))
        self._save_state()

    def set_language(self, code: str) -> None:
        i18n.set_language(code)
        self.config.set("language", code)
        self.config.save()
        self.tray.retranslate()
        self.tray.set_paused(self.alerts.is_paused(time.time()))
        self.tray.set_autostart_checked(autostart.is_enabled())
        # Labels live in the views, so re-render them from the current data.
        self.tray.update_views(self.views)
        self.panel.update_views(self.views)

    def _set_autostart(self, enabled: bool) -> None:
        ok = autostart.enable() if enabled else autostart.disable()
        if not ok:
            log.warning("could not %s autostart", "enable" if enabled else "disable")
        self.tray.set_autostart_checked(autostart.is_enabled())

    def _open_log(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.log_file())))

    # -- presentation ----------------------------------------------------------

    def _show_welcome(self) -> None:
        """Tell the user, once, that something is now running invisibly."""
        from .ui.popup import Toast

        actions: list[tuple[str, Any]] = []
        if sys.platform == "win32":
            # New tray icons hide in the overflow area, where nobody finds them.
            actions.append((i18n.t("welcome.tray_settings"), _open_tray_settings))
        actions.append((i18n.t("welcome.ack"), lambda: None))

        self.toasts.show(
            Toast(
                title=i18n.t("welcome.title"),
                body=i18n.t("welcome.body"),
                tier="green",
                sticky=True,
                actions=actions,
            )
        )
        self.tray.show_message(i18n.t("welcome.title"), i18n.t("welcome.body"))
        self._state["welcomed"] = True
        self._save_state()

    def _on_tray_unavailable(self) -> None:
        log.warning("no system tray host available; running with popups only")
        from .ui.popup import Toast

        self.toasts.show(
            Toast(
                title=i18n.t("notify.info_title"),
                body=i18n.t("welcome.title"),
                detail=i18n.t("welcome.body"),
                tier="orange",
                sticky=True,
                actions=[(i18n.t("welcome.ack"), lambda: None)],
            )
        )

    # -- IPC -------------------------------------------------------------------

    def _handle_command(self, command: str) -> dict:
        if command == ipc.CMD_SHOW:
            self.show_panel()
        elif command == ipc.CMD_REFRESH:
            self.refresh(force=True)
        elif command == ipc.CMD_TEST:
            self.show_test_alert()
        elif command == ipc.CMD_STOP:
            self.quit()
        return {
            "ok": True,
            "pid": os.getpid(),
            "paused": self.alerts.is_paused(time.time()),
            "providers": [
                {
                    "provider": view.provider,
                    "title": view.title,
                    "status": view.status.value,
                    "message": view.message,
                    "source": view.source,
                    "windows": [
                        {
                            "key": row.key,
                            "label": row.label,
                            "remaining": row.remaining,
                            "text": row.remaining_text,
                            "tier": row.tier,
                            "refills": row.refills,
                            "burns": row.burns,
                            "pace": row.pace,
                        }
                        for row in view.rows
                    ],
                    "notes": view.notes,
                }
                for view in self.views
            ],
        }

    # -- state -----------------------------------------------------------------

    def _save_state(self) -> None:
        self._state["alerts"] = self.alerts.to_dict()
        paths.atomic_write_json(paths.state_file(), self._state)


def _load_state() -> dict:
    return paths.read_json(paths.state_file()) or {}


def _initial_language(config: Config) -> str:
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


def _select_platform_plugin(config: Config) -> None:
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


def _open_tray_settings() -> None:
    QDesktopServices.openUrl(QUrl("ms-settings:taskbar"))


def _configure_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        paths.log_file(), maxBytes=512_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger("tokentray")
    root.setLevel(logging.INFO)
    root.handlers = [handler]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
