"""Serialized provider polling and explicit notification preview requests."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from .core.cache import Cache
from .core.config import Config
from .core.models import Snapshot, Status

log = logging.getLogger("tokentray")


class PollWorker(QObject):
    """Fetches every provider, one poll at a time, off the UI thread."""

    snapshots_ready = Signal(list)
    refresh_finished = Signal(bool)
    requested = Signal(bool)
    test_requested = Signal()
    test_finished = Signal(object)

    def __init__(self, config: Config) -> None:
        super().__init__()
        from .providers import build_providers

        self._providers = build_providers(config, Cache())
        self._busy = False
        self._pending: bool | None = None
        self.requested.connect(self._run)
        self.test_requested.connect(self._run_test)

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
    def _run_test(self) -> None:
        """Runs on the same worker thread, after any in-flight regular poll."""
        snapshots: list[Snapshot] | None = None
        try:
            snapshots = []
            for provider in self._providers:
                try:
                    snapshots.append(provider.fetch(force=True))
                except Exception:
                    log.exception("notification test fetch failed: %s", provider.id)
                    snapshots.append(Snapshot(provider=provider.id, status=Status.ERROR))
        except Exception:
            log.exception("notification test failed")
            snapshots = None
        finally:
            self.test_finished.emit(snapshots)

    @Slot()
    def shutdown(self) -> None:
        for provider in self._providers:
            provider.close()
