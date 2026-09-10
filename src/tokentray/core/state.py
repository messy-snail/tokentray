"""The bookkeeping tokentray keeps about itself between runs.

Deliberately not part of ``Config``: this is not settings a person edits but a
ledger the app rewrites on every poll, and mixing the two invites hand-edits to a
file that gets clobbered within one poll interval. Keeping the file's shape in
one place is also what lets the CLI clear a single entry without re-deriving what
the rest of the document looks like.
"""

from __future__ import annotations

from typing import Any

from . import paths
from .alerts import AlertState

WELCOMED = "welcomed"
ALERTS = "alerts"


def load() -> dict[str, Any]:
    return paths.read_json(paths.state_file()) or {}


def save(data: dict[str, Any]) -> None:
    paths.atomic_write_json(paths.state_file(), data)


def clear_welcome(data: dict[str, Any]) -> None:
    """Re-arm the one-time first-run notice.

    Pops the key rather than writing ``False``: the gate in ``Controller.start``
    tests truthiness, and an explicit ``False`` would read as "already shown" to
    anything that later checks for presence instead of for truth.
    """
    data.pop(WELCOMED, None)


def clear_alerts(data: dict[str, Any]) -> None:
    """Forget which thresholds and reminders have already fired."""
    data[ALERTS] = AlertState.from_dict(data.get(ALERTS)).cleared().to_dict()
