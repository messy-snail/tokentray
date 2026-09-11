"""Application bootstrap and wiring.

Threading rule for this file: the poller thread produces Snapshots and nothing
else. Every widget touch happens on the main thread, reached only through a
queued signal. Network calls and keyring reads both block — the first for
seconds on a bad connection, the second indefinitely on a Linux SecretService
prompt — so neither may ever run where the UI lives.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

from PySide6.QtCore import (
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

from . import autostart, bootstrap, ipc
from .core import i18n, paths, state
from .core.alerts import AlertState, evaluate
from .core.cache import Cache
from .core.config import Config
from .core.models import Status
from .core.view import ProviderView, build_view

log = logging.getLogger("tokentray")


def main(autostart_launch: bool = False, **kwargs: Any) -> int:
    """Entry point for both ``tokentray`` and ``tokentray-gui``."""
    if "autostart" in kwargs:
        autostart_launch = bool(kwargs["autostart"])
    if "--autostart" in sys.argv:
        autostart_launch = True

    # Answered before Qt exists: this is the one thing a packaging smoke test can
    # ask a windowed binary, and building a QApplication to answer it would start
    # an event loop the caller has no way to end.
    if "--version" in sys.argv or "-V" in sys.argv:
        from . import __version__

        print(f"tokentray {__version__}")
        return 0

    config = Config.load()
    bootstrap.configure_logging()
    bootstrap.select_platform_plugin(config)

    from .ui import icons
    from .ui.fonts import initialize_fonts

    QApplication.setApplicationName("tokentray")
    QApplication.setApplicationDisplayName("tokentray")
    QApplication.setDesktopFileName(autostart.APP_ID)
    app = QApplication(sys.argv)
    initialize_fonts(app)
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
    refresh_finished = Signal(bool)
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
                if force:
                    self.refresh_finished.emit(all(s.status == Status.OK for s in snapshots))
                if self._pending is None:
                    return
                force, self._pending = self._pending, None
        except Exception:
            log.exception("poll failed")
            if force:
                self.refresh_finished.emit(False)
        finally:
            self._busy = False

    @Slot()
    def shutdown(self) -> None:
        for provider in self._providers:
            provider.close()


class Controller(QObject):
    """Owns application state and connects the pieces.

    A QObject, and deliberately so: the poll thread reaches the UI through
    ``snapshots_ready``, and Qt can only queue that onto the main thread if the
    receiver has a thread affinity to queue it to. A plain Python receiver has
    none, so Qt would call the slot directly on the poll thread - which paints
    widgets from the wrong thread and aborts outright on macOS, where AppKit
    refuses to build an NSWindow off the main thread.
    """

    def __init__(self, app, config: Config, *, autostart_launch: bool = False) -> None:
        super().__init__()
        self.app = app
        self.config = config
        self.autostart_launch = autostart_launch
        self.views: list[ProviderView] = []

        self._state = state.load()
        self.alerts = AlertState.from_dict(self._state.get("alerts"))

        i18n.set_language(bootstrap.initial_language(config))

        from .notify.dispatcher import Dispatcher
        from .notify.webhook import Webhook
        from .ui.panel import DetailPanel
        from .ui.popup import ToastManager
        from .ui.tray import Tray

        self.tray = Tray()
        self.panel = DetailPanel(on_refresh=lambda: self.refresh(force=True))
        self.toasts = ToastManager(
            duration=config.popup_duration,
            position=config.popup_position,
            anchor_widget_geometry=self.tray.geometry,
        )
        self.toasts.on_activated = self.show_panel
        from .login_recovery import LoginRecovery

        self.recovery = LoginRecovery(config, lambda: self.refresh(force=True), self)
        self.panel.recovery = self.recovery
        self.toasts.login_actions = lambda key: self.recovery.toast_actions(key, self.show_panel)
        self.recovery.changed.connect(lambda: self.panel.update_views(self.views))
        self.webhook = Webhook.from_config(config)
        self.dispatcher = Dispatcher(
            self.toasts,
            self.webhook,
            native=self.tray.show_message,
            native_enabled=bool(config.get("native_notifications", True)),
        )

        self._thread = QThread()
        self._worker = PollWorker(config)
        self._worker.moveToThread(self._thread)
        self._worker.snapshots_ready.connect(self._on_snapshots)
        self._worker.refresh_finished.connect(self.panel.refresh_feedback.finish)

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
        self.recovery.start()
        self.tray.set_autostart_checked(autostart.is_enabled())
        self.tray.set_paused(self.alerts.is_paused(time.time()))
        self.tray.unavailable.connect(self._on_tray_unavailable)
        self.tray.start()

        # One line at startup so "no notification ever appeared" can be answered
        # from the log alone - whether the channel was even plausible here, not
        # merely whether something got around to calling it.
        from . import diagnostics

        log.info(
            "native notifications: %s",
            diagnostics.native_report(self.config, inspect_signature=False).summary(),
        )

        self._thread.start()
        self._timer.start()
        self.refresh(force=False)

        if not self.autostart_launch and not self._state.get("welcomed"):
            self._show_welcome()
        self.app.aboutToQuit.connect(self._shutdown)
        return True

    def _shutdown(self) -> None:
        self.recovery.close()
        self._timer.stop()
        self.toasts.clear()
        self.webhook.close()
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
        self.recovery.on_views(self.views)
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
        self.tray.integration_requested.connect(self.show_integration_settings)
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

        samples = (
            ("claude", "Claude Code", "test.claude_body", "green", 0.62, "3h 42m"),
            ("codex", "Codex", "test.codex_body", "orange", 0.38, "2d 7h"),
        )
        for provider_id, provider, body_key, tier, fraction, reset in samples:
            self.toasts.show(
                Toast(
                    title=i18n.t("fmt.notify_title", provider=provider),
                    provider=provider_id,
                    body=i18n.t(body_key),
                    tier=tier,
                    fraction=fraction,
                    detail=i18n.t("fmt.refills", dur=reset),
                    duration=self.config.popup_duration,
                )
            )

        # Also poke the OS notification centre. The toasts above prove the app can
        # draw, which is exactly what still works when the native channel is dead;
        # only this line can tell those two failures apart. One message, not one
        # per provider: macOS coalesces near-identical banners anyway, and the
        # question is just whether anything arrived at all.
        self.dispatcher.notify_native(i18n.t("notify.info_title"), i18n.t("test.body"))

    def show_integration_settings(self) -> None:
        from .ui.integration import IntegrationDialog

        existing = getattr(self, "_integration_dialog", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return
        dialog = IntegrationDialog(self.config, on_saved=self._apply_webhook_settings)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._integration_dialog = dialog

    def _apply_webhook_settings(self, settings) -> None:
        self.webhook.reconfigure(
            enabled=settings.enabled,
            kind=settings.kind,
            url=settings.url,
            configured=settings.configured,
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
        detail = ""
        if sys.platform == "win32":
            # New tray icons hide in the overflow area, where nobody finds them.
            actions.append((i18n.t("welcome.tray_settings"), bootstrap.open_tray_settings))
        elif sys.platform == "darwin":
            # Stock macOS shows the icon, but a menu bar manager hides new items
            # by default - the same "where did it go" as the Windows overflow,
            # with no settings URL to offer because it belongs to another app.
            detail = i18n.t("welcome.menu_bar_manager")
        actions.append((i18n.t("welcome.ack"), lambda: None))

        self.toasts.show(
            Toast(
                title=i18n.t("welcome.title"),
                body=i18n.t("welcome.body"),
                detail=detail,
                tier="green",
                sticky=True,
                actions=actions,
            )
        )
        # Through the dispatcher, not the tray directly: somebody who set
        # native_notifications = false should not be handed an OS banner on
        # their very first run.
        self.dispatcher.notify_native(i18n.t("welcome.title"), i18n.t("welcome.body"))
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
        elif command == ipc.CMD_RELOAD_CONFIG:
            self.config = Config.load()
            self.webhook.reconfigure_from_config(self.config)
            # Thresholds and reminders are read from self.config on every poll,
            # so they are live the moment it is replaced. The native gate and the
            # toast presentation live in other objects and have to be handed over.
            # Poll interval and language still need a restart.
            self.dispatcher.set_native_enabled(
                bool(self.config.get("native_notifications", True))
            )
            self.toasts.duration = self.config.popup_duration
            self.toasts.position = self.config.popup_position
        elif command == ipc.CMD_RESET_WELCOME:
            # Applied to the in-memory copy, because the next poll rewrites the
            # whole file and would otherwise resurrect what the CLI just cleared.
            state.clear_welcome(self._state)
            self._save_state()
        elif command == ipc.CMD_RESET_ALERTS:
            self.alerts = self.alerts.cleared()
            self._save_state()
        elif command == ipc.CMD_STOP:
            # Let IPC send its reply before shutdown destroys the socket.
            QTimer.singleShot(0, self.quit)
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
        state.save(self._state)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
