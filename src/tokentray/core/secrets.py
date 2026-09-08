"""Manually-entered credential storage.

Only used for the manual-entry path — when tokentray reads the Claude Code or
Codex CLI's own credential files it does not copy them here, so there is exactly
one copy of those secrets on disk and it stays owned by the tool that refreshes it.

``keyring`` is imported lazily: on Linux it can block on a SecretService prompt,
and importing it at module scope would drag that into CLI start-up.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from . import paths

SERVICE = "tokentray"

CLAUDE_ACCESS_TOKEN = "claude.access_token"
CODEX_ACCESS_TOKEN = "codex.access_token"
CODEX_REFRESH_TOKEN = "codex.refresh_token"
CODEX_ACCOUNT_ID = "codex.account_id"
WEBHOOK_URL = "webhook.url"

_fallback_warned = False


class SecretStore:
    """Keyring-backed store that degrades to an owner-only TOML file.

    Headless Linux without a SecretService daemon is the common case for the
    fallback; a session there still deserves working credentials, just with a
    visible warning that they are sitting in a plain file.
    """

    def __init__(self, fallback_path: Path | None = None) -> None:
        self._fallback_path = fallback_path
        self._backend: str | None = None
        self._use_fallback = False

    # -- public API ------------------------------------------------------------

    def get(self, name: str) -> str | None:
        if not self._use_fallback:
            keyring = self._keyring()
            if keyring is not None:
                try:
                    value = keyring.get_password(SERVICE, name)
                    if value:
                        return value
                except Exception:
                    self._switch_to_fallback("read failed")
        return self._fallback_read().get(name) or None

    def set(self, name: str, value: str) -> None:
        if not self._use_fallback:
            keyring = self._keyring()
            if keyring is not None:
                try:
                    keyring.set_password(SERVICE, name, value)
                    return
                except Exception:
                    self._switch_to_fallback("write failed")
        data = self._fallback_read()
        data[name] = value
        self._fallback_write(data)

    def delete(self, name: str) -> None:
        if not self._use_fallback:
            keyring = self._keyring()
            if keyring is not None:
                try:
                    keyring.delete_password(SERVICE, name)
                except Exception:
                    pass
        data = self._fallback_read()
        if data.pop(name, None) is not None:
            self._fallback_write(data)

    def backend_name(self) -> str:
        """Human-readable backend, for ``tokentray doctor``."""
        if self._use_fallback:
            return f"file ({self._path()})"
        keyring = self._keyring()
        if keyring is None:
            return f"file ({self._path()})"
        return self._backend or "unknown"

    @property
    def using_fallback(self) -> bool:
        return self._use_fallback

    # -- internals -------------------------------------------------------------

    def _keyring(self) -> Any | None:
        try:
            import keyring
            from keyring.errors import NoKeyringError
        except Exception:
            self._switch_to_fallback("keyring not importable")
            return None
        try:
            backend = keyring.get_keyring()
            # keyring always returns *something*; the fail backend is its way of
            # saying "no store on this box", and it raises only once you use it.
            if backend.__class__.__module__.rsplit(".", 1)[-1] == "fail":
                raise NoKeyringError("no usable backend")
            self._backend = f"{backend.__class__.__module__}.{backend.__class__.__name__}"
        except Exception:
            self._switch_to_fallback("no usable keyring backend")
            return None
        return keyring

    def _switch_to_fallback(self, reason: str) -> None:
        global _fallback_warned
        self._use_fallback = True
        if not _fallback_warned:
            _fallback_warned = True
            import logging

            logging.getLogger("tokentray").warning(
                "Keyring unavailable (%s); storing secrets in %s with owner-only permissions.",
                reason,
                self._path(),
            )

    def _path(self) -> Path:
        return self._fallback_path or paths.secrets_file()

    def _fallback_read(self) -> dict[str, str]:
        try:
            with self._path().open("rb") as fh:
                loaded = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            return {}
        return {k: str(v) for k, v in loaded.items() if isinstance(v, str)}

    def _fallback_write(self, data: dict[str, str]) -> None:
        paths.atomic_write_text(self._path(), tomli_w.dumps(data), private=True)


_default: SecretStore | None = None


def default_store() -> SecretStore:
    global _default
    if _default is None:
        _default = SecretStore()
    return _default
