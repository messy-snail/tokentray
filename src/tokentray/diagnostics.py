"""Answers for "is this thing actually working?".

Every line here exists because something failed silently in the field: a
credentials file that exists but holds no token, a tray host that is simply not
there, an OS notification channel that accepts a call and delivers nothing. The
job is to turn each of those into a sentence someone can read, which is why this
lives apart from the CLI that prints it - the app's own startup log asks the same
questions.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__

# Bounded because `doctor` is something a person waits on: a hung codesign must
# not hold the whole report hostage, and "unknown" is a perfectly good answer.
CODESIGN_TIMEOUT = 2.0

MACOS_CONSEQUENCE = (
    "Notification Centre delivery is unreliable on macOS; "
    "the in-app toast is the primary channel"
)


def report(config) -> list[str]:
    from .core import paths
    from .core.secrets import default_store
    from .providers.claude import credentials_path
    from .providers.codex import auth_path

    lines = [f"tokentray {__version__}  (python {sys.version.split()[0]}, {sys.platform})"]

    claude_file = credentials_path()
    lines.append(f"claude credentials  {credential_state(claude_file, 'claude')}  {claude_file}")
    if sys.platform == "darwin":
        lines.append("                    (falls back to the macOS login keychain)")
    codex_file = auth_path()
    lines.append(f"codex credentials   {credential_state(codex_file, 'codex')}  {codex_file}")

    lines.append(f"secret backend      {default_store().backend_name()}")
    lines.append(f"config              {paths.config_file()}")
    lines.append(f"poll interval       {config.poll_interval}s (cache ttl {config.cache_ttl}s)")
    lines.append(f"language            {config.language}")
    lines.append(f"thresholds          {config.thresholds}")
    lines.append(f"remind before       {config.remind_before or 'off'}")

    facts = qt_facts()
    lines.append(f"tray                {_tray_line(facts)}")
    lines.extend(_native_lines(config, facts))
    return lines


def credential_state(path, provider: str) -> str:
    """Distinguish "no file", "file but no token", and "usable".

    The empty-token case is real: Claude Code writes the file with plan metadata
    but leaves accessToken blank when the session is authenticated elsewhere
    (for example through the desktop app), and "missing" would be misleading.
    """
    import json

    if not path.exists():
        return "missing"
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return "unreadable"
    if provider == "claude":
        token = (data.get("claudeAiOauth") or {}).get("accessToken")
    else:
        token = (data.get("tokens") or {}).get("access_token")
    if not token:
        return "no token in file"
    return "found"


def qt_facts() -> dict[str, Any]:
    """Everything that needs a QApplication, gathered in one trip.

    Creating the application is the expensive part and it can only happen once, so
    the tray answer and the notification answer come from the same visit.
    """
    try:
        from PySide6.QtWidgets import QApplication, QSystemTrayIcon
    except Exception as exc:  # pragma: no cover - depends on the install
        return {"error": f"PySide6 unavailable ({type(exc).__name__})"}
    # A QApplication is required before querying either capability. A CLI process
    # exits right after, so there is nothing to tear down; inside the app this
    # returns the one already running.
    qapp = QApplication.instance() or QApplication([])
    return {
        "platform": qapp.platformName(),
        "tray": QSystemTrayIcon.isSystemTrayAvailable(),
        "supports_messages": QSystemTrayIcon.supportsMessages(),
    }


# -- native notification delivery ---------------------------------------------


@dataclass(frozen=True)
class NativeReport:
    enabled: bool  # the native_notifications setting
    supported: bool | None  # supportsMessages(); None when Qt could not be reached
    bundle: Path | None
    signature: str  # "signed (TEAM)" | "ad-hoc" | "unsigned" | "unknown" | "n/a"

    def summary(self) -> str:
        parts = [f"enabled={self.enabled}", f"supportsMessages={_maybe(self.supported)}"]
        if sys.platform == "darwin":
            parts.append(f"bundle={self.bundle or 'none'}")
            parts.append(f"signature={self.signature}")
        return ", ".join(parts)


def native_report(
    config, *, inspect_signature: bool, facts: dict[str, Any] | None = None
) -> NativeReport:
    """Whether an OS notification stands any chance of being delivered here.

    ``inspect_signature`` is the only thing that costs a subprocess, so the app's
    startup path leaves it off and settles for "unknown".
    """
    if facts is None:
        facts = qt_facts()
    supported = None if "error" in facts else bool(facts["supports_messages"])
    bundle = macos_bundle()
    if bundle is None:
        signature = "n/a"
    elif inspect_signature:
        signature = bundle_signature(bundle)
    else:
        signature = "unknown"
    return NativeReport(
        enabled=bool(config.get("native_notifications", True)),
        supported=supported,
        bundle=bundle,
        signature=signature,
    )


def macos_bundle() -> Path | None:
    """The .app this process runs from, if it runs from one at all.

    Pure pathlib on purpose - this is asked at startup, where spawning anything
    would be indefensible. Requiring the executable to sit directly in
    Contents/MacOS is what stops a checkout that merely lives underneath someone
    else's bundle (a python inside Xcode.app, say) from claiming to be one.
    """
    if sys.platform != "darwin":
        return None
    exe = Path(sys.executable).resolve()
    if exe.parent.name != "MacOS":
        return None
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent if (parent / "Contents" / "Info.plist").exists() else None
    return None


def bundle_signature(bundle: Path) -> str:
    """Whether the bundle carries a real identity, an ad-hoc one, or none.

    Only a Developer ID gives macOS a reason to trust the app, and only codesign
    can tell the three apart - but the free check runs first, so an unsigned
    bundle costs no subprocess at all.
    """
    if not (bundle / "Contents" / "_CodeSignature" / "CodeResources").exists():
        return "unsigned"
    try:
        text = _codesign(bundle)
    except Exception:
        return "unknown"
    if "not signed at all" in text:
        return "unsigned"
    if "Signature=adhoc" in text:
        return "ad-hoc"
    for line in text.splitlines():
        if line.startswith("TeamIdentifier="):
            team = line.split("=", 1)[1].strip()
            if team and team != "not set":
                return f"signed ({team})"
    return "unknown"


def _codesign(bundle: Path) -> str:
    """Seam, so tests can answer for signatures they have no way to produce."""
    proc = subprocess.run(
        ["/usr/bin/codesign", "-dv", "--verbose=2", str(bundle)],
        capture_output=True,
        text=True,
        timeout=CODESIGN_TIMEOUT,
        check=False,
    )
    return proc.stdout + proc.stderr


# -- line formatting ----------------------------------------------------------


def _tray_line(facts: dict[str, Any]) -> str:
    if "error" in facts:
        return facts["error"]
    available = "available" if facts["tray"] else "NOT available"
    return f"{available} (platform: {facts['platform']})"


def _native_lines(config, facts: dict[str, Any]) -> list[str]:
    native = native_report(config, inspect_signature=True, facts=facts)
    state = "on" if native.enabled else "off"
    lines = [f"native alerts       {state}  (supportsMessages={_maybe(native.supported)})"]
    if sys.platform != "darwin":
        return lines
    if native.bundle is None:
        lines.append(f"app bundle          none - running from {sys.executable}")
        lines.append(
            "                    macOS delivers tray notifications only from a signed .app bundle"
        )
    else:
        lines.append(f"app bundle          {native.bundle} ({native.signature})")
    lines.append(f"                    {MACOS_CONSEQUENCE}")
    lines.append("                    check System Settings -> Notifications -> tokentray as well")
    return lines


def _maybe(value: object) -> str:
    return "unknown" if value is None else str(value)
