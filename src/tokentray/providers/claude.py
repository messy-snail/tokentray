"""Claude Code quota provider.

Reads the OAuth token that Claude Code itself maintains. tokentray never
refreshes that token: Claude Code owns it, refreshes it on its own schedule, and
two writers racing over one credential file is how people get logged out. When
it expires we say so and point the user at ``claude``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.compute import WINDOW_5H, WINDOW_7D, parse_timestamp
from ..core.models import ExtraUsage, Snapshot, Status, UsageWindow
from ..core.secrets import CLAUDE_ACCESS_TOKEN, SecretStore, default_store
from .base import BaseProvider, CredentialsUnreadable, ProviderError, SchemaError

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN_SERVICE = "Claude Code-credentials"
KEYCHAIN_ITEM_NOT_FOUND = 44  # errSecItemNotFound, as `security` exits for a missing item

# Set once the keychain refuses a read. While access is refused, each `security`
# call can bring the authorization prompt back, and both the poll timer and the
# two-second login probe would otherwise keep calling it. Only a read the user
# asked for tries again; a successful read clears this.
_keychain_refused = threading.Event()


@dataclass
class ClaudeCreds:
    access_token: str
    subscription: str | None = None
    expires_at: float | None = None   # epoch seconds
    source: str = "file"


class ClaudeProvider(BaseProvider):
    id = "claude"

    def __init__(self, *args: Any, secrets: SecretStore | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._secrets = secrets or default_store()

    # -- credentials -----------------------------------------------------------

    def credentials(self, *, interactive: bool = False) -> ClaudeCreds | None:
        creds = _from_file(credentials_path())
        refused = False
        if creds is None and sys.platform == "darwin":
            if interactive or not _keychain_refused.is_set():
                try:
                    creds = _from_keychain()
                    _keychain_refused.clear()
                except CredentialsUnreadable:
                    _keychain_refused.set()
                    refused = True
            else:
                refused = True
        if creds is None:
            token = self._secrets.get(CLAUDE_ACCESS_TOKEN)
            if token:
                creds = ClaudeCreds(access_token=token, source="manual")
        if creds is None and refused:
            raise CredentialsUnreadable("keychain")
        return creds

    def precheck(self, creds: ClaudeCreds) -> Status | None:
        # Saves a guaranteed-401 round trip, and lets us name the fix precisely.
        if creds.expires_at is not None and creds.expires_at <= time.time():
            return Status.EXPIRED
        return None

    # -- network ---------------------------------------------------------------

    def fetch_live(self, creds: ClaudeCreds) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {creds.access_token}",
            "anthropic-beta": str(self.config.get("claude.beta_header", "oauth-2025-04-20")),
        }
        response = self.client().get(USAGE_URL, headers=headers)
        if response.status_code == 200:
            try:
                body = response.json()
            except ValueError as exc:
                raise SchemaError(f"invalid JSON: {exc}") from exc
            if not isinstance(body, dict):
                raise SchemaError("response was not an object")
            body["_subscription"] = creds.subscription
            return body
        if response.status_code == 401:
            raise ProviderError(Status.UNAUTHORIZED, "HTTP 401")
        if response.status_code == 429:
            raise ProviderError(Status.RATE_LIMITED, "HTTP 429")
        raise ProviderError(Status.ERROR, f"HTTP {response.status_code}")

    # -- parsing ---------------------------------------------------------------

    def parse(self, body: dict[str, Any]) -> Snapshot:
        five_hour = body.get("five_hour")
        if not isinstance(five_hour, dict) or five_hour.get("utilization") is None:
            raise SchemaError("five_hour.utilization missing")

        windows: list[UsageWindow] = [
            _window("claude.5h", five_hour, WINDOW_5H),
        ]
        # A seven-day window is not guaranteed: some plans report only the 5h one.
        for key, qualifier, field, gate in (
            ("claude.7d", "", "seven_day", False),
            ("claude.7d_opus", "Opus", "seven_day_opus", True),
            ("claude.7d_sonnet", "Sonnet", "seven_day_sonnet", True),
        ):
            block = body.get(field)
            if not isinstance(block, dict) or block.get("utilization") is None:
                continue
            # Per-model sub-limits stay hidden until the model is actually used,
            # otherwise every account shows two permanently-full rows. They run
            # the same seven days as the main window, so an unused one adds a
            # row without adding anything to read.
            if gate and int(_as_float(block.get("utilization"))) <= 0:
                continue
            windows.append(_window(key, block, WINDOW_7D, qualifier=qualifier))

        return Snapshot(
            provider=self.id,
            status=Status.OK,
            windows=windows,
            plan=body.get("_subscription") or None,
            extra=_extra_usage(body.get("spend")),
        )


def credentials_path() -> Path:
    """Location of Claude Code's credential file, honouring CLAUDE_CONFIG_DIR."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(override).expanduser() if override else Path.home() / ".claude"
    return base / ".credentials.json"


def _from_file(path: Path) -> ClaudeCreds | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return _from_blob(data, source="file")


def _from_keychain() -> ClaudeCreds | None:
    """macOS stores the same JSON blob in the login keychain instead of a file.

    A missing item only means nobody is logged in. Any other failure - access
    refused, a prompt nobody answered - is raised: retrying cannot succeed
    without the user and may bring the prompt back each time.
    """
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # `security` blocks while its authorization prompt is up.
        raise CredentialsUnreadable("keychain") from exc
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode == KEYCHAIN_ITEM_NOT_FOUND:
        return None
    if result.returncode != 0:
        raise CredentialsUnreadable("keychain")
    if not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
    except ValueError:
        return None
    return _from_blob(data, source="keychain")


def _from_blob(data: Any, source: str) -> ClaudeCreds | None:
    if not isinstance(data, dict):
        return None
    oauth = data.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return None
    token = oauth.get("accessToken")
    if not isinstance(token, str) or not token:
        return None
    return ClaudeCreds(
        access_token=token,
        subscription=oauth.get("subscriptionType") or None,
        expires_at=_expiry_seconds(oauth.get("expiresAt")),
        source=source,
    )


def _expiry_seconds(value: Any) -> float | None:
    """Normalise ``expiresAt`` to epoch seconds; Claude Code writes milliseconds."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number / 1000.0 if number > 1e11 else number


def _window(
    key: str, block: dict[str, Any], window_secs: int, *, qualifier: str = ""
) -> UsageWindow:
    return UsageWindow(
        key=key,
        used_pct=_as_float(block.get("utilization")),
        resets_at=parse_timestamp(block.get("resets_at")),
        window_secs=window_secs,
        qualifier=qualifier,
    )


def _extra_usage(spend: Any) -> ExtraUsage | None:
    """Pay-as-you-go balance. Amounts arrive in minor units with an exponent."""
    if not isinstance(spend, dict):
        return None
    limit = spend.get("limit")
    if not isinstance(limit, dict) or limit.get("amount_minor") is None:
        return None
    try:
        exponent = int(limit.get("exponent", 2))
    except (TypeError, ValueError):
        exponent = 2
    divisor = 10.0**exponent
    used_block = spend.get("used") if isinstance(spend.get("used"), dict) else {}
    return ExtraUsage(
        enabled=bool(spend.get("enabled", False)),
        used=_as_float(used_block.get("amount_minor")) / divisor,
        limit=_as_float(limit.get("amount_minor")) / divisor,
        currency=str(limit.get("currency") or "USD"),
    )


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
