from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tokentray.core import view as view_mod
from tokentray.core.alerts import AlertState, evaluate
from tokentray.core.models import Snapshot, Status, UsageWindow

NOW_DT = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
NOW = 1_757_246_400.0
THRESHOLDS = [50, 25, 10]
REMIND = [60, 30, 10]


def make_view(
    *,
    used: float = 0.0,
    resets_in: float | None = 7200,
    window_secs: int = 18_000,
    status: Status = Status.OK,
    provider: str = "claude",
    key: str = "claude.5h",
):
    windows = []
    if status.has_data:
        windows = [
            UsageWindow(
                key=key,
                used_pct=used,
                resets_at=NOW_DT + timedelta(seconds=resets_in) if resets_in is not None else None,
                window_secs=window_secs,
            )
        ]
    return view_mod.build_view(
        Snapshot(provider=provider, status=status, windows=windows), NOW_DT
    )


def run(views, state, *, thresholds=THRESHOLDS, remind=REMIND, now=NOW):
    if not isinstance(views, list):
        views = [views]
    return evaluate(
        views,
        thresholds=thresholds,
        remind_before=remind,
        state=state,
        now=now,
        clock=NOW_DT,
    )


@pytest.fixture
def seeded() -> AlertState:
    """A state that has already absorbed one full-quota poll."""
    state = AlertState()
    run(make_view(used=0.0), state)
    assert state.seeded
    return state


class TestSeeding:
    def test_first_poll_is_silent(self):
        state = AlertState()
        # Starting the app at 76% used must not replay 50% and 25%.
        assert run(make_view(used=76.0), state) == []
        assert state.seeded is True

    def test_seeding_adopts_the_lowest_crossed_level(self):
        state = AlertState()
        run(make_view(used=76.0), state)     # 24% remaining
        assert state.threshold["claude.5h"] == 25
        # ...so the next alert is 10%, not a repeat of 25%.
        events = run(make_view(used=92.0), state)
        assert [e.priority for e in events] == ["urgent"]

    def test_actionable_status_still_speaks_on_the_first_poll(self):
        state = AlertState()
        events = run(make_view(status=Status.EXPIRED), state)
        assert [e.kind for e in events] == ["info"]


class TestThresholds:
    def test_crossing_fires_once(self, seeded):
        assert len(run(make_view(used=55.0), seeded)) == 1
        assert run(make_view(used=56.0), seeded) == []

    def test_a_sharp_drop_reports_the_worst_level_reached(self, seeded):
        # The reference implementation stepped down one level per tick and would
        # have said "50%" here, four minutes before admitting it was 5%.
        events = run(make_view(used=95.0), seeded)
        assert len(events) == 1
        assert "5%" in events[0].body
        assert events[0].priority == "urgent"

    def test_each_level_fires_on_the_way_down(self, seeded):
        levels = []
        for used in (55.0, 80.0, 92.0):
            levels += [e.priority for e in run(make_view(used=used), seeded)]
        assert levels == ["default", "high", "urgent"]

    def test_window_refill_re_arms_every_level(self, seeded):
        run(make_view(used=95.0), seeded)
        run(make_view(used=0.0), seeded)                 # window reset
        assert seeded.threshold["claude.5h"] == 100
        assert len(run(make_view(used=55.0), seeded)) == 1

    @pytest.mark.parametrize(
        "used,priority", [(51.0, "default"), (76.0, "high"), (91.0, "urgent")]
    )
    def test_priority_follows_the_level(self, seeded, used, priority):
        assert run(make_view(used=used), seeded)[0].priority == priority

    def test_every_window_is_tracked_independently(self):
        # Upstream only alerted on Claude's two windows; Codex was display-only.
        state = AlertState()
        codex = make_view(provider="codex", key="codex.primary", used=0.0)
        run([make_view(used=0.0), codex], state)
        events = run(
            [make_view(used=55.0), make_view(provider="codex", key="codex.primary", used=80.0)],
            state,
        )
        assert {e.key for e in events} == {"claude.5h", "codex.primary"}
        assert {e.provider for e in events} == {"claude", "codex"}
        assert {e.title for e in events} == {"tokentray · Claude Code", "tokentray · Codex"}


class TestReminders:
    """Reminders fire near a reset, so every case here holds usage still.

    The activity signal is a usage delta between polls, which means a test that
    also moves usage is testing suppression whether it meant to or not.
    """

    @pytest.fixture
    def idle(self):
        """State that has seen one poll at 10% used, so nothing looks active."""
        state = AlertState()
        run(make_view(used=10.0, resets_in=4 * 3600), state)
        return state

    def test_fires_inside_the_first_window(self, idle):
        events = run(make_view(used=10.0, resets_in=45 * 60), idle)
        assert [e.kind for e in events] == ["reminder"]
        assert idle.remind["claude.5h"] == 60

    def test_each_level_fires_once(self, idle):
        kinds = []
        for mins in (45, 20, 5):
            kinds += [e.kind for e in run(make_view(used=10.0, resets_in=mins * 60), idle)]
        assert kinds == ["reminder", "reminder", "reminder"]
        assert run(make_view(used=10.0, resets_in=5 * 60), idle) == []

    def test_usage_still_moving_suppresses_the_nudge(self, idle):
        # Usage climbed since the last poll: they are at the keyboard, so
        # "your quota is about to refill" is noise rather than news.
        events = run(make_view(used=14.0, resets_in=45 * 60), idle)
        assert [e.kind for e in events] == []
        # The level is still consumed, so it cannot fire late once they stop.
        assert idle.remind["claude.5h"] == 60

    def test_noise_sized_movement_does_not_count_as_active(self, idle):
        events = run(make_view(used=10.01, resets_in=45 * 60), idle)
        assert [e.kind for e in events] == ["reminder"]

    def test_pace_is_the_fallback_without_a_previous_sample(self):
        # First poll after a restart has no delta to measure. Pace can only
        # exceed 1.3x when a good chunk of the window is left, which for a short
        # (Codex-style) window can still coincide with a reminder level.
        state = AlertState(seeded=True)
        events = run(make_view(used=80.0, resets_in=50 * 60, window_secs=7200), state)
        assert "reminder" not in [e.kind for e in events]

    def test_new_window_re_arms(self, idle):
        run(make_view(used=10.0, resets_in=45 * 60), idle)
        run(make_view(used=10.0, resets_in=4 * 3600), idle)   # fresh window
        assert idle.remind["claude.5h"] == 999

    def test_empty_configuration_disables_reminders(self, idle):
        assert run(make_view(used=10.0, resets_in=45 * 60), idle, remind=[]) == []

    def test_past_reset_does_not_remind(self, idle):
        assert run(make_view(used=10.0, resets_in=-60), idle) == []


class TestPause:
    def test_paused_state_delivers_nothing(self, seeded):
        seeded.paused_until = NOW + 3600
        assert run(make_view(used=95.0), seeded) == []

    def test_pause_still_advances_state_so_resuming_is_quiet(self, seeded):
        seeded.paused_until = NOW + 3600
        run(make_view(used=95.0), seeded)
        assert seeded.threshold["claude.5h"] == 10
        # Resumed, unchanged usage: nothing has happened since, so stay quiet.
        seeded.paused_until = 0.0
        assert run(make_view(used=95.0), seeded) == []


class TestStatusAlerts:
    def test_reported_once_per_occurrence(self, seeded):
        assert len(run(make_view(status=Status.EXPIRED), seeded)) == 1
        assert run(make_view(status=Status.EXPIRED), seeded) == []

    def test_recovery_re_arms_the_notice(self, seeded):
        run(make_view(status=Status.EXPIRED), seeded)
        run(make_view(used=0.0), seeded)                  # back to normal
        assert len(run(make_view(status=Status.EXPIRED), seeded)) == 1

    def test_a_changed_problem_is_reported_again(self, seeded):
        run(make_view(status=Status.EXPIRED), seeded)
        events = run(make_view(status=Status.SCHEMA_CHANGED), seeded)
        assert len(events) == 1

    def test_transient_failures_stay_quiet(self, seeded):
        # Rate limiting and network errors resolve themselves; only things the
        # user can act on are worth a popup.
        assert run(make_view(status=Status.RATE_LIMITED), seeded) == []
        assert run(make_view(status=Status.ERROR), seeded) == []


class TestStatePersistence:
    def test_round_trip_through_a_plain_dict(self, seeded):
        run(make_view(used=95.0), seeded)
        restored = AlertState.from_dict(seeded.to_dict())
        assert restored.threshold == seeded.threshold
        assert restored.seeded is True
        # A restored state must not re-announce what it already said.
        assert run(make_view(used=95.0), restored) == []

    def test_junk_state_file_does_not_crash(self):
        state = AlertState.from_dict({"threshold": "nonsense", "paused_until": "soon"})
        assert state.threshold == {}
        assert state.paused_until == 0.0
