"""OpenAI Codex quota provider.

Unlike Claude, the Codex CLI's access token can be refreshed with the refresh
token sitting next to it — but doing so means writing to ``auth.json``, a file
the Codex CLI also owns. That write is opt-in (``codex.refresh``) and guarded
against clobbering a concurrent write by the CLI itself.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.compute import parse_timestamp
from ..core.models import Credits, Snapshot, Status, UsageWindow
from ..core.paths import atomic_write_json
from ..core.secrets import (
    CODEX_ACCESS_TOKEN,
    CODEX_ACCOUNT_ID,
    CODEX_REFRESH_TOKEN,
    SecretStore,
    default_store,
)
from .base import BaseProvider, ProviderError, SchemaError

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


@dataclass
class CodexCreds:
    access_token: str
    account_id: str | None = None
    refresh_token: str | None = None
    path: Path | None = None      # None when the token came from manual entry
    mtime: float | None = None


class CodexProvider(BaseProvider):
    id = "codex"

    def __init__(self, *args: Any, secrets: SecretStore | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._secrets = secrets or default_store()

    # -- credentials -----------------------------------------------------------

    def credentials(self, *, interactive: bool = False) -> CodexCreds | None:
        creds = _from_file(auth_path())
        if creds is not None:
            return creds
        token = self._secrets.get(CODEX_ACCESS_TOKEN)
        if not token:
            return None
        return CodexCreds(
            access_token=token,
            account_id=self._secrets.get(CODEX_ACCOUNT_ID),
            refresh_token=self._secrets.get(CODEX_REFRESH_TOKEN),
        )

    # -- network ---------------------------------------------------------------

    def fetch_live(self, creds: CodexCreds) -> dict[str, Any]:
        response = self._get_usage(creds.access_token, creds.account_id)
        if response.status_code == 401:
            refreshed = self._maybe_refresh(creds)
            if refreshed is None:
                raise ProviderError(Status.EXPIRED, "HTTP 401")
            response = self._get_usage(refreshed, creds.account_id)

        if response.status_code == 200:
            try:
                body = response.json()
            except ValueError as exc:
                raise SchemaError(f"invalid JSON: {exc}") from exc
            if not isinstance(body, dict):
                raise SchemaError("response was not an object")
            return body
        if response.status_code == 401:
            raise ProviderError(Status.EXPIRED, "HTTP 401")
        if response.status_code == 429:
            raise ProviderError(Status.RATE_LIMITED, "HTTP 429")
        raise ProviderError(Status.ERROR, f"HTTP {response.status_code}")

    def _get_usage(self, token: str, account_id: str | None) -> Any:
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "codex_cli_rs",
            "originator": "codex_cli_rs",
            "Accept": "application/json",
        }
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id
        return self.client().get(USAGE_URL, headers=headers)

    def _maybe_refresh(self, creds: CodexCreds) -> str | None:
        """Exchange the refresh token, and persist the result only if it is safe.

        Returns the new access token, or None when refreshing is disabled or
        impossible. The re-read before writing catches the case where the Codex
        CLI refreshed the same file while our request was in flight.
        """
        if not self.config.get("codex.refresh", False):
            return None
        if not creds.refresh_token:
            return None

        response = self.client().post(
            TOKEN_URL,
            json={
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": creds.refresh_token,
            },
            headers={"Content-Type": "application/json"},
        )
        if response.status_code != 200:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        access = payload.get("access_token")
        if not isinstance(access, str) or not access:
            return None

        if creds.path is not None:
            self._write_back(creds, payload)
        else:
            self._secrets.set(CODEX_ACCESS_TOKEN, access)
            if isinstance(payload.get("refresh_token"), str):
                self._secrets.set(CODEX_REFRESH_TOKEN, payload["refresh_token"])
        return access

    def _write_back(self, creds: CodexCreds, payload: dict[str, Any]) -> None:
        path = creds.path
        assert path is not None
        try:
            current_mtime = path.stat().st_mtime
        except OSError:
            return
        if creds.mtime is not None and current_mtime != creds.mtime:
            # Someone else (almost certainly the Codex CLI) rewrote the file
            # while we were refreshing. Their token wins; ours is still valid
            # for this run, so use it in memory and leave the file alone.
            return
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or not isinstance(data.get("tokens"), dict):
            return
        tokens = data["tokens"]
        tokens["access_token"] = payload["access_token"]
        for field in ("id_token", "refresh_token"):
            value = payload.get(field)
            if isinstance(value, str) and value:
                tokens[field] = value
        data["last_refresh"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        atomic_write_json(path, data, private=True)

    # -- parsing ---------------------------------------------------------------

    def parse(self, body: dict[str, Any]) -> Snapshot:
        rate_limit = body.get("rate_limit")
        if not isinstance(rate_limit, dict):
            raise SchemaError("rate_limit missing")
        primary = rate_limit.get("primary_window")
        if not isinstance(primary, dict) or primary.get("used_percent") is None:
            raise SchemaError("rate_limit.primary_window.used_percent missing")

        windows = _windows_from("codex", rate_limit)
        # Exclude Spark before building snapshots so it cannot affect any
        # display, tray colour or alert. Keep other sub-limits even at 0%.
        for index, entry in enumerate(_as_list(body.get("additional_rate_limits"))):
            if not isinstance(entry, dict) or _is_spark(entry):
                continue
            slug = _slug(entry.get("metered_feature"), entry.get("limit_name"), index)
            windows.extend(
                _windows_from(
                    f"codex.{slug}",
                    entry.get("rate_limit"),
                    qualifier=_short_name(entry.get("limit_name")),
                )
            )
        windows.extend(
            _windows_from(
                "codex.code_review",
                body.get("code_review_rate_limit"),
                qualifier="Code Review",
            )
        )

        return Snapshot(
            provider=self.id,
            status=Status.OK,
            windows=windows,
            plan=str(body.get("plan_type") or "codex"),
            credits=_credits(body.get("credits")),
        )


def auth_path() -> Path:
    """Location of the Codex CLI credential file, honouring CODEX_HOME."""
    override = os.environ.get("CODEX_HOME")
    base = Path(override).expanduser() if override else Path.home() / ".codex"
    return base / "auth.json"


def _from_file(path: Path) -> CodexCreds | None:
    try:
        stat = path.stat()
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    tokens = data.get("tokens")
    # API-key mode has no `tokens` block; the usage endpoint needs a session
    # token, so there is nothing we can do with an API key here.
    if not isinstance(tokens, dict):
        return None
    access = tokens.get("access_token")
    if not isinstance(access, str) or not access:
        return None
    return CodexCreds(
        access_token=access,
        account_id=tokens.get("account_id") or None,
        refresh_token=tokens.get("refresh_token") or None,
        path=path,
        mtime=stat.st_mtime,
    )


def _windows_from(
    prefix: str, rate_limit: Any, *, qualifier: str = ""
) -> list[UsageWindow]:
    """Both slots of one ``rate_limit`` block, skipping the ones not reported.

    Every bucket in the response has this shape - the account's own quota, each
    per-model sub-limit, code review - so they all come through here and get
    keys that differ only by prefix.
    """
    if not isinstance(rate_limit, dict):
        return []
    windows = []
    for slot in ("primary", "secondary"):
        block = rate_limit.get(f"{slot}_window")
        if not isinstance(block, dict) or block.get("used_percent") is None:
            continue
        windows.append(_window(f"{prefix}.{slot}", block, qualifier=qualifier))
    return windows


def _window(key: str, block: dict[str, Any], *, qualifier: str = "") -> UsageWindow:
    try:
        window_secs = int(block.get("limit_window_seconds") or 0)
    except (TypeError, ValueError):
        window_secs = 0
    return UsageWindow(
        key=key,
        used_pct=_as_float(block.get("used_percent")),
        resets_at=parse_timestamp(block.get("reset_at")),
        window_secs=window_secs,
        qualifier=qualifier,
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_spark(entry: dict[str, Any]) -> bool:
    feature = entry.get("metered_feature")
    return (
        isinstance(feature, str) and feature.strip().casefold() == "codex_bengalfox"
    ) or _short_name(entry.get("limit_name")).casefold() == "spark"


def _slug(feature: Any, limit_name: Any, index: int) -> str:
    """Stable key fragment for one sub-limit.

    This ends up in the alert key, which is what alert state is stored under, so
    it has to survive restarts and reorderings. ``metered_feature`` is the
    API's own identifier and the best candidate; the index is a last resort that
    only stays stable while the list does.
    """
    for candidate in (feature, limit_name):
        if isinstance(candidate, str) and candidate.strip():
            return re.sub(r"[^a-z0-9]+", "_", candidate.strip().lower()).strip("_")
    return f"extra{index}"


def _short_name(limit_name: Any) -> str:
    """``GPT-5.3-Codex-Spark`` -> ``Spark``.

    Claude labels its sub-limits ``Opus`` and ``Sonnet`` rather than the full
    model id; the distinctive tail is what a person recognises, and it is what
    fits in a tooltip Windows cuts off at 128 characters.
    """
    if not isinstance(limit_name, str) or not limit_name.strip():
        return ""
    return limit_name.strip().rsplit("-", 1)[-1]


def _credits(block: Any) -> Credits | None:
    if not isinstance(block, dict):
        return None
    if block.get("unlimited") is True:
        return Credits(unlimited=True)
    if block.get("has_credits") is True and block.get("balance") is not None:
        return Credits(balance=_as_float(block.get("balance")))
    return None


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
