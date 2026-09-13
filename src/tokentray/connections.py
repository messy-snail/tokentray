"""Local CLI and credential discovery shared by setup, diagnostics and recovery."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .core.config import Config
from .core.models import Status
from .core.secrets import SecretStore
from .providers.base import BaseProvider


class AuthState(str, Enum):
    MISSING = "missing"
    EXPIRED = "expired"
    UNREADABLE = "unreadable"
    UNSUPPORTED = "unsupported"
    FOUND = "found"
    CONNECTED = "connected"


class Action(str, Enum):
    LOGIN = "login"
    INSTALL = "install"
    RECHECK = "recheck"
    CANCEL = "cancel"
    COPY = "copy"


NAMES = {"claude": "Claude Code", "codex": "Codex"}
INSTALL_URLS = {
    "claude": "https://code.claude.com/docs/en/setup",
    "codex": "https://developers.openai.com/codex/cli/",
}
LOGIN_ARGS = {"claude": ("auth", "login"), "codex": ("login",)}


@dataclass(frozen=True)
class Connection:
    provider: str
    executable: Path | None
    source: str
    auth: AuthState

    @property
    def action(self) -> Action:
        return Action.LOGIN if self.executable else Action.INSTALL


@dataclass(frozen=True)
class Observation:
    connection: Connection
    # Used only in memory to detect credential replacement, never in UI/logs.
    fingerprint: str = field(repr=False, default="")


def find_cli(provider: str) -> Path | None:
    """Search PATH, then bounded standard installation locations."""
    if provider not in NAMES:
        raise ValueError("Unknown provider")
    found = shutil.which(provider)
    if found:
        return Path(found).absolute()
    home = Path.home()
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        roaming = Path(os.environ.get("APPDATA", home / "AppData/Roaming"))
        candidates = [home / ".local/bin" / f"{provider}.exe",
                      roaming / "npm" / f"{provider}.cmd"]
        if provider == "codex":
            candidates.append(local / "Programs/OpenAI/Codex/bin/codex.exe")
    else:
        candidates = [home / ".local/bin" / provider, home / ".npm-global/bin" / provider,
                      Path("/opt/homebrew/bin") / provider, Path("/usr/local/bin") / provider]
    return next((p.absolute() for p in candidates if p.is_file()
                 and (sys.platform == "win32" or os.access(p, os.X_OK))), None)


def make_provider(provider: str, config: Config, store: SecretStore | None = None) -> BaseProvider:
    from .providers.claude import ClaudeProvider
    from .providers.codex import CodexProvider

    return {"claude": ClaudeProvider, "codex": CodexProvider}[provider](config, secrets=store)


def _expired_jwt(token: str) -> bool:
    """Use a declared expiry only as a local hint, never as proof of authentication."""
    try:
        payload = token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        expiry = data.get("exp") if isinstance(data, dict) else None
        return isinstance(expiry, (int, float)) and expiry <= time.time()
    except (IndexError, ValueError, UnicodeError):
        return False


def _file_state(path: Path, provider: str) -> AuthState:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return AuthState.MISSING
    except (OSError, ValueError):
        return AuthState.UNREADABLE
    if not isinstance(data, dict):
        return AuthState.UNREADABLE
    if provider == "codex" and data.get("OPENAI_API_KEY") and not data.get("tokens"):
        return AuthState.UNSUPPORTED
    return AuthState.MISSING


def observe(
    provider: str, config: Config, store: SecretStore | None = None, *, interactive: bool = False,
) -> Observation:
    """Read credentials using the provider's own precedence, without network I/O."""
    from .providers.base import CredentialsUnreadable
    from .providers.claude import credentials_path
    from .providers.codex import auth_path

    executable = find_cli(provider)
    path = credentials_path() if provider == "claude" else auth_path()
    reader = make_provider(provider, config, store)
    try:
        creds = reader.credentials(interactive=interactive)
        if creds is None:
            return Observation(Connection(provider, executable, "file", _file_state(path, provider)))
        source = creds.source if provider == "claude" else ("file" if creds.path else "manual")
        auth = AuthState.EXPIRED if reader.precheck(creds) == Status.EXPIRED else AuthState.FOUND
        if provider == "codex" and _expired_jwt(creds.access_token):
            auth = AuthState.EXPIRED
        identity = (creds.access_token, getattr(creds, "expires_at", None),
                    getattr(creds, "account_id", None), source)
        digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        return Observation(Connection(provider, executable, source, auth), digest)
    except CredentialsUnreadable as exc:
        return Observation(Connection(provider, executable, exc.detail, AuthState.UNREADABLE))
    except (OSError, ValueError, TypeError):
        return Observation(Connection(provider, executable, "unknown", AuthState.UNREADABLE))
    finally:
        reader.close()


def inspect(provider: str, config: Config, store: SecretStore | None = None) -> Connection:
    return observe(provider, config, store).connection


def keychain_refused(observation: Observation) -> bool:
    """True when macOS refused the keychain read, as opposed to finding no credentials."""
    connection = observation.connection
    return connection.source == "keychain" and connection.auth == AuthState.UNREADABLE


def login_command(provider: str) -> str:
    return " ".join((provider, *LOGIN_ARGS[provider]))
