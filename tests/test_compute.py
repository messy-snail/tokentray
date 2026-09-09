from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tokentray.core import compute
from tokentray.core.models import UsageWindow

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def window(used: float, *, resets_in: float | None, window_secs: int = compute.WINDOW_5H) -> UsageWindow:
    resets_at = NOW + timedelta(seconds=resets_in) if resets_in is not None else None
    return UsageWindow(
        key="test", used_pct=used, resets_at=resets_at, window_secs=window_secs
    )


class TestRemainingAndTier:
    @pytest.mark.parametrize(
        "used,expected", [(0, 100.0), (48.0, 52.0), (100, 0.0), (33.35, 66.7)]
    )
    def test_remaining(self, used, expected):
        assert compute.remaining_pct(used) == expected

    @pytest.mark.parametrize(
        "remaining,tier",
        [
            (100, compute.TIER_GREEN),
            (50.9, compute.TIER_ORANGE),  # truncated to 50 -> orange boundary
            (51, compute.TIER_GREEN),
            (20, compute.TIER_RED),
            (20.9, compute.TIER_RED),
            (21, compute.TIER_ORANGE),
            (0, compute.TIER_RED),
        ],
    )
    def test_tier_boundaries(self, remaining, tier):
        assert compute.tier_for(remaining) == tier


class TestPace:
    def test_halfway_through_window_at_half_usage_is_sustainable(self):
        stats = compute.derive(window(50.0, resets_in=compute.WINDOW_5H / 2), NOW)
        assert stats.pace == 1.0

    def test_double_speed(self):
        # Half the window elapsed but all of the quota spent.
        stats = compute.derive(window(100.0, resets_in=compute.WINDOW_5H / 2), NOW)
        assert stats.pace == 2.0

    def test_no_usage_yields_no_pace(self):
        assert compute.derive(window(0.0, resets_in=1000), NOW).pace is None

    def test_window_not_started_yields_no_pace(self):
        # resets_in == window length means zero elapsed time.
        assert compute.derive(window(10.0, resets_in=compute.WINDOW_5H), NOW).pace is None

    def test_past_reset_yields_no_pace(self):
        assert compute.derive(window(10.0, resets_in=-60), NOW).pace is None

    def test_missing_reset_yields_no_pace(self):
        assert compute.derive(window(10.0, resets_in=None), NOW).pace is None


class TestBurnout:
    def test_projection_matches_linear_extrapolation(self):
        # 25% used over the first half of a 5h window -> 75% left lasts 3x as long.
        stats = compute.derive(window(25.0, resets_in=compute.WINDOW_5H / 2), NOW)
        assert stats.burnout_secs == pytest.approx(compute.WINDOW_5H * 1.5, rel=1e-6)

    def test_exhausted_window_has_no_projection(self):
        stats = compute.derive(window(100.0, resets_in=compute.WINDOW_5H / 2), NOW)
        assert stats.exhausted is True
        assert stats.burnout_secs is None


class TestFormatting:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (None, ""),
            (0, ""),
            (-5, ""),
            (59, "0m"),
            (600, "10m"),
            (3_600, "1h 0m"),
            (13_320, "3h 42m"),
            (90_000, "1d 1h"),
        ],
    )
    def test_format_duration(self, seconds, expected):
        assert compute.format_duration(seconds) == expected

    def test_progress_bar_width_and_fill(self):
        bar = compute.progress_bar(52.0)
        assert len(bar) == 20
        assert bar.count(compute.BAR_FILLED) == 10

    @pytest.mark.parametrize("remaining,filled", [(0, 0), (100, 20), (4.9, 0), (5, 1)])
    def test_progress_bar_edges(self, remaining, filled):
        assert compute.progress_bar(remaining).count(compute.BAR_FILLED) == filled

    def test_local_reset_is_empty_once_past(self):
        assert compute.format_local_reset(NOW - timedelta(minutes=1), NOW) == ""

    def test_local_reset_same_day_omits_date(self):
        text = compute.format_local_reset(NOW + timedelta(seconds=60), NOW)
        assert text and ":" in text and text[0].isdigit()


class TestWindowAbbr:
    @pytest.mark.parametrize(
        "seconds,label",
        [
            (compute.WINDOW_5H, "5h"),
            (compute.WINDOW_7D, "7d"),
            (86_400, "1d"),
            (259_200, "3d"),
            (3_600, "1h"),
            (43_200, "12h"),
            (0, "limit"),
            (None, "limit"),
            (90, "limit"),
        ],
    )
    def test_labels_follow_reported_duration(self, seconds, label):
        assert compute.window_abbr(seconds) == label


class TestParseTimestamp:
    @pytest.mark.parametrize(
        "value",
        [
            "2026-09-07T12:00:00Z",
            "2026-09-07T12:00:00+00:00",
            "2026-09-07T12:00:00.123456Z",
            "2026-09-07T21:00:00+09:00",
            1_788_000_000,
        ],
    )
    def test_accepts_every_shape_both_apis_emit(self, value):
        parsed = compute.parse_timestamp(value)
        assert parsed is not None and parsed.tzinfo is not None

    @pytest.mark.parametrize("value", [None, "", "not-a-date", True, {}])
    def test_rejects_junk(self, value):
        assert compute.parse_timestamp(value) is None

    def test_offset_is_normalised_to_utc(self):
        a = compute.parse_timestamp("2026-09-07T21:00:00+09:00")
        b = compute.parse_timestamp("2026-09-07T12:00:00Z")
        assert a == b


class TestPaceIcon:
    @pytest.mark.parametrize(
        "pace,expected", [(None, ""), (0.5, "\U0001F422"), (1.0, "✅"), (1.5, "⚡"), (3.0, "\U0001F525")]
    )
    def test_thresholds(self, pace, expected):
        assert compute.pace_icon(pace) == expected
