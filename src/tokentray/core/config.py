"""User configuration, stored as TOML next to the platform's other config.

Reads are total: a corrupt or partial file degrades to defaults rather than
stopping the app from starting, because a tray app that refuses to launch gives
the user nowhere to fix the problem from.
"""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from . import paths

DEFAULTS: dict[str, Any] = {
    "language": "en",
    "poll_interval": 120,
    "thresholds": [50, 25, 10],
    "remind_before": [60, 30, 10],
    "native_notifications": True,
    "popup": {
        "position": "auto",   # auto | bottom-right | top-right | off
        "duration": 8,
    },
    "claude": {
        "enabled": True,
        "beta_header": "oauth-2025-04-20",
    },
    "codex": {
        "enabled": True,
        # Refreshing rewrites ~/.codex/auth.json, which the Codex CLI also owns.
        # Off by default: an unexpected write to someone else's credential file
        # is a worse failure than showing a "login expired" notice.
        "refresh": False,
    },
    "webhook": {
        "enabled": False,
        "kind": "ntfy",       # ntfy | generic
        "url": "",
    },
    "linux": {
        # Wayland ignores client-side window placement, so toasts land wherever
        # the compositor likes. XWayland honours it.
        "force_xwayland": True,
    },
}

MIN_POLL_INTERVAL = 30
CACHE_TTL_SKEW = 10


class Config:
    """Dotted-path access over the merged defaults + user file."""

    def __init__(self, data: dict[str, Any] | None = None, path: Path | None = None) -> None:
        self._data = _merge(copy.deepcopy(DEFAULTS), data or {})
        self._path = path

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or paths.config_file()
        data: dict[str, Any] = {}
        try:
            with path.open("rb") as fh:
                data = tomllib.load(fh)
        except FileNotFoundError:
            pass
        except (OSError, tomllib.TOMLDecodeError):
            # Keep going on defaults; `tokentray doctor` surfaces the bad file.
            data = {}
        return cls(data, path)

    def save(self, path: Path | None = None) -> Path:
        target = path or self._path or paths.config_file()
        paths.atomic_write_text(target, tomli_w.dumps(self._data))
        self._path = target
        return target

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self._data
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    # -- typed accessors for the values read on every poll ---------------------

    @property
    def poll_interval(self) -> int:
        """Seconds between refreshes, floored so we cannot hammer the API."""
        try:
            return max(MIN_POLL_INTERVAL, int(self.get("poll_interval", 120)))
        except (TypeError, ValueError):
            return 120

    @property
    def cache_ttl(self) -> int:
        """Slightly under the poll interval so timer jitter never skips a refresh."""
        return max(0, self.poll_interval - CACHE_TTL_SKEW)

    @property
    def thresholds(self) -> list[int]:
        return _int_list(self.get("thresholds"), DEFAULTS["thresholds"])

    @property
    def remind_before(self) -> list[int]:
        return _int_list(self.get("remind_before"), DEFAULTS["remind_before"])

    @property
    def language(self) -> str:
        value = self.get("language")
        return value if isinstance(value, str) else "en"

    @property
    def popup_duration(self) -> int:
        try:
            return max(2, int(self.get("popup.duration", 8)))
        except (TypeError, ValueError):
            return 8


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def _int_list(value: Any, fallback: list[int]) -> list[int]:
    """Coerce a config list to sorted-descending ints, ignoring junk entries."""
    if not isinstance(value, (list, tuple)):
        return list(fallback)
    out: list[int] = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return sorted(set(out), reverse=True)


def parse_value(raw: str) -> Any:
    """Best-effort scalar parsing for ``tokentray config set key value``."""
    lowered = raw.strip().lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if "," in raw:
        return _int_list([p for p in raw.split(",")], []) or [p.strip() for p in raw.split(",")]
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw
