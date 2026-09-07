"""Filesystem locations and atomic write helpers.

Every directory the app writes to is resolved here so the rest of the code never
builds a path by hand. Lock/socket files deliberately avoid the cache directory:
cleaners wipe caches, and a vanished lock file breaks single-instance detection.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from platformdirs import (
    user_cache_dir,
    user_config_dir,
    user_log_dir,
    user_runtime_dir,
    user_state_dir,
)

APP_NAME = "tokentray"
APP_ID = "io.github.messy-snail.tokentray"


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    return _ensure(Path(user_config_dir(APP_NAME, appauthor=False)))


def cache_dir() -> Path:
    return _ensure(Path(user_cache_dir(APP_NAME, appauthor=False)))


def state_dir() -> Path:
    return _ensure(Path(user_state_dir(APP_NAME, appauthor=False)))


def log_dir() -> Path:
    return _ensure(Path(user_log_dir(APP_NAME, appauthor=False)))


def runtime_dir() -> Path:
    """Directory for the lock file and IPC socket.

    XDG_RUNTIME_DIR is the right home for these on Linux; elsewhere platformdirs
    aliases it to a cache path, so fall back to the state directory instead.
    """
    if sys.platform.startswith("linux"):
        try:
            return _ensure(Path(user_runtime_dir(APP_NAME, appauthor=False)))
        except Exception:  # pragma: no cover - exotic environments only
            pass
    return state_dir()


def config_file() -> Path:
    return config_dir() / "config.toml"


def state_file() -> Path:
    return state_dir() / "state.json"


def secrets_file() -> Path:
    return config_dir() / "secrets.toml"


def log_file() -> Path:
    return log_dir() / "tokentray.log"


def cache_file(provider_id: str) -> Path:
    return cache_dir() / f"{provider_id}.json"


def lock_file() -> Path:
    return runtime_dir() / "tokentray.lock"


def atomic_write_text(path: Path, text: str, *, private: bool = False) -> None:
    """Write ``text`` to ``path`` via a temp file in the same directory, then rename.

    A half-written config or credential file is worse than a stale one, so the
    replace only happens once the bytes are on disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if private:
            _chmod_600(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, data: object, *, private: bool = False) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2), private=private)


def read_json(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            loaded = json.load(fh)
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _chmod_600(path: Path) -> None:
    """Best-effort owner-only permissions. A no-op where POSIX modes don't apply."""
    try:
        os.chmod(path, 0o600)
    except (OSError, NotImplementedError):  # pragma: no cover - Windows/odd filesystems
        pass
