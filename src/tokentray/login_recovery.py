"""Non-blocking local credential observation and login recovery for Qt surfaces."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
import time
from typing import Callable
import webbrowser

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from .connections import Action, AuthState, Connection, INSTALL_URLS, NAMES, Observation, observe, login_command
from .core.config import Config
from .core.i18n import t
from .core.models import Status
from .core.view import ProviderView
from .login_terminal import LaunchError, launch

AUTH_REQUIRED = {Status.NOT_CONFIGURED, Status.EXPIRED, Status.UNAUTHORIZED}


@dataclass
class Session:
    connection: Connection | None = None
    fingerprint: str = field(default="", repr=False)
    waiting: bool = False
    changed: bool = False
    deadline: float = 0
    message: str = ""
    status: Status | None = None
    generation: int = 0


class LoginRecovery(QObject):
    """Keep all Qt mutations on the owning thread and all credential I/O off it."""

    changed = Signal()

    def __init__(self, config: Config, refresh: Callable[[], None], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.refresh = refresh
        self.sessions = {key: Session() for key in NAMES}
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="login-recovery")
        self._jobs: dict[str, tuple[Future[Observation], str, int]] = {}
        self._queued: dict[str, str] = {}
        self._next_probe = 0.0
        self._closed = False
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if self._closed or self._timer.isActive():
            return
        self._timer.start()
        for key in NAMES:
            if self.config.get(f"{key}.enabled", True):
                self._submit(key, "probe")

    def _submit(self, key: str, kind: str) -> None:
        if self._closed or key in self._jobs:
            return
        generation = self.sessions[key].generation
        self._jobs[key] = (self._pool.submit(self._work, key, kind), kind, generation)

    def _work(self, key: str, kind: str) -> Observation:
        observation = observe(key, self.config)
        if kind == "login" and observation.connection.executable:
            launch(key, observation.connection.executable)
        return observation

    def _tick(self) -> None:
        for key, (future, kind, generation) in list(self._jobs.items()):
            if not future.done():
                continue
            del self._jobs[key]
            session = self.sessions[key]
            if generation != session.generation:
                continue
            try:
                result = future.result()
            except Exception as exc:
                session.waiting = False
                session.message = (str(exc) if isinstance(exc, LaunchError)
                                   else "unreadable" if kind != "login" else "terminal_failed")
                self.changed.emit()
                continue
            old_fingerprint = session.fingerprint
            old_presentation = (session.connection, session.waiting, session.message)
            session.connection = result.connection
            session.fingerprint = result.fingerprint
            if kind == "login":
                session.waiting = result.connection.executable is not None
                session.changed = False
                session.deadline = time.monotonic() + 300
                session.message = "waiting" if session.waiting else "path_hint"
            elif session.waiting and result.fingerprint and old_fingerprint != result.fingerprint:
                session.changed = True
                session.message = "changed"
                self.refresh()
            elif kind == "recheck":
                session.message = "waiting" if session.waiting else ""
                self.refresh()
            if old_presentation != (session.connection, session.waiting, session.message):
                self.changed.emit()
        now = time.monotonic()
        for session in self.sessions.values():
            if session.waiting and now >= session.deadline:
                session.waiting = False
                session.message = "timeout"
                self.changed.emit()
        for key, kind in list(self._queued.items()):
            if key not in self._jobs:
                del self._queued[key]
                self._submit(key, kind)
        if now >= self._next_probe:
            self._next_probe = now + 2
            for key, session in self.sessions.items():
                if session.waiting:
                    self._submit(key, "probe")

    def on_views(self, views: list[ProviderView]) -> None:
        for view in views:
            session = self.sessions[view.provider]
            session.status = view.status
            if view.status == Status.OK and (not session.waiting or session.changed):
                session.waiting = False
                session.message = ""
                if session.connection:
                    session.connection = replace(session.connection, auth=AuthState.CONNECTED)
            elif session.waiting and session.changed and view.status not in AUTH_REQUIRED:
                session.message = "network"

    def message(self, key: str) -> str:
        session = self.sessions[key]
        if session.message:
            return t("connect." + session.message)
        if not session.connection:
            return t("connect.checking")
        return t("connect.hint", provider=NAMES[key]) if session.connection.executable else t("connect.path_hint")

    def actions(self, key: str) -> list[tuple[str, Callable[[], None]]]:
        session = self.sessions[key]
        if session.waiting:
            actions = [Action.RECHECK, Action.CANCEL]
        elif self._queued.get(key) == "login" or (key in self._jobs and self._jobs[key][1] == "login"):
            return []
        elif session.message in ("terminal_failed", "terminal_missing"):
            actions = [Action.COPY, Action.LOGIN]
        elif session.connection:
            actions = [session.connection.action, Action.RECHECK]
        else:
            actions = [Action.LOGIN, Action.RECHECK]
        return [(t("connect." + action.value), lambda a=action: self.activate(key, a)) for action in actions]

    def toast_actions(self, key: str, show_panel: Callable[[], None]) -> list[tuple[str, Callable[[], None]]]:
        def activate(handler: Callable[[], None]) -> None:
            handler()
            show_panel()

        return [(label, lambda fn=handler: activate(fn)) for label, handler in self.actions(key)]

    def activate(self, key: str, action: Action) -> None:
        session = self.sessions[key]
        if action == Action.INSTALL:
            webbrowser.open(INSTALL_URLS[key])
        elif action == Action.COPY:
            QApplication.clipboard().setText(login_command(key))
        elif action == Action.CANCEL:
            session.generation += 1
            self._queued.pop(key, None)
            session.waiting = False
            session.message = ""
        elif action == Action.RECHECK:
            if key in self._jobs:
                self._queued.setdefault(key, "recheck")
            else:
                self._submit(key, "recheck")
        elif action == Action.LOGIN and not session.waiting:
            session.message = "checking"
            if key not in self._jobs:
                self._submit(key, "login")
            elif self._jobs[key][1] != "login":
                self._queued[key] = "login"
        self.changed.emit()

    def close(self) -> None:
        self._closed = True
        self._timer.stop()
        for session in self.sessions.values():
            session.waiting = False
        self._pool.shutdown(wait=False, cancel_futures=True)
