from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tokentray.core import i18n, view
from tokentray.core.cache import Cache
from tokentray.core.config import DEFAULTS, Config, parse_value
from tokentray.core.models import Snapshot, Status, UsageWindow
from tokentray.core.secrets import SecretStore

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


class TestI18nParity:
    def test_every_locale_defines_every_key(self):
        english = set(i18n.STRINGS["en"])
        for code, table in i18n.STRINGS.items():
            assert set(table) == english, f"{code} key set differs"

    def test_format_placeholders_match_across_locales(self):
        # A translated string that drops {pct} would silently render a message
        # with no number in it, which no test of t() alone would catch.
        for key, english in i18n.STRINGS["en"].items():
            expected = i18n.placeholders(english)
            for code, table in i18n.STRINGS.items():
                assert i18n.placeholders(table[key]) == expected, f"{code}:{key}"

    def test_no_empty_translations(self):
        for code, table in i18n.STRINGS.items():
            for key, value in table.items():
                assert value.strip(), f"{code}:{key} is empty"

    @pytest.mark.parametrize(
        "raw,expected", [("ko", "ko"), ("ko_KR", "ko"), ("ko-KR.UTF-8", "ko"), ("fr", "en"), (None, "en")]
    )
    def test_locale_normalisation(self, raw, expected):
        assert i18n.normalize(raw) == expected

    def test_unknown_key_returns_the_key(self):
        assert i18n.t("no.such.key") == "no.such.key"

    def test_missing_format_argument_does_not_raise(self):
        assert i18n.t("fmt.remaining") == i18n.STRINGS["en"]["fmt.remaining"]

    def test_korean_renders(self):
        i18n.set_language("ko")
        assert i18n.t("fmt.notify", label="7일 윈도우", pct=25) == "7일 윈도우: 25% 남음"


class TestConfig:
    def test_defaults_are_present_without_a_file(self, tmp_path):
        config = Config.load(tmp_path / "absent.toml")
        assert config.poll_interval == DEFAULTS["poll_interval"]
        assert config.get("codex.refresh") is False

    def test_corrupt_file_degrades_to_defaults(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("this is not = valid = toml", encoding="utf-8")
        # A tray app that refuses to start leaves the user nowhere to fix it from.
        assert Config.load(path).poll_interval == 120

    def test_user_values_merge_over_nested_defaults(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("[codex]\nrefresh = true\n", encoding="utf-8")
        config = Config.load(path)
        assert config.get("codex.refresh") is True
        assert config.get("codex.enabled") is True  # untouched default survives

    def test_round_trip_through_disk(self, tmp_path):
        path = tmp_path / "config.toml"
        config = Config.load(path)
        config.set("language", "ko")
        config.save()
        assert Config.load(path).language == "ko"

    def test_poll_interval_has_a_floor(self):
        assert Config({"poll_interval": 1}).poll_interval == 30

    def test_cache_ttl_sits_just_under_the_poll_interval(self):
        config = Config({"poll_interval": 300})
        assert config.cache_ttl == 290

    def test_threshold_list_is_sorted_descending_and_deduped(self):
        assert Config({"thresholds": [10, 50, 25, 25, "x"]}).thresholds == [50, 25, 10]

    @pytest.mark.parametrize(
        "raw,expected", [("true", True), ("off", False), ("300", 300), ("1.5", 1.5), ("ko", "ko")]
    )
    def test_scalar_parsing(self, raw, expected):
        assert parse_value(raw) == expected


class TestCache:
    def test_store_then_load_round_trip(self, tmp_path):
        cache = Cache(tmp_path)
        cache.store("claude", {"a": 1}, now=1000.0)
        entry = cache.load("claude")
        assert entry is not None and entry.body == {"a": 1}
        assert entry.is_fresh(110, now=1050.0)
        assert not entry.is_fresh(110, now=1200.0)

    def test_failure_preserves_the_body_and_arms_backoff(self, tmp_path):
        cache = Cache(tmp_path)
        cache.store("claude", {"a": 1}, now=1000.0)
        kept = cache.mark_failure("claude", ttl=110, note="HTTP 429", now=1200.0)
        assert kept is not None and kept.body == {"a": 1}
        entry = cache.load("claude")
        assert entry is not None
        assert entry.in_backoff(now=1250.0)
        assert not entry.in_backoff(now=1400.0)
        # fetched_at must not move, or a stale read would look fresh.
        assert entry.fetched_at == 1000.0
        assert entry.note == "HTTP 429"

    def test_failure_without_prior_body_returns_nothing_to_show(self, tmp_path):
        cache = Cache(tmp_path)
        assert cache.mark_failure("claude", ttl=110, note="boom", now=1000.0) is None

    def test_unreadable_file_is_treated_as_empty(self, tmp_path):
        (tmp_path / "claude.json").write_text("{{{", encoding="utf-8")
        assert Cache(tmp_path).load("claude") is None


class TestSecretStoreFallback:
    def test_falls_back_to_an_owner_only_file(self, tmp_path, monkeypatch):
        # A headless Linux box with no SecretService: keyring loads, but hands
        # back its fail backend, which raises on first use.
        import keyring
        from keyring.backends import fail

        monkeypatch.setattr(keyring, "get_keyring", lambda: fail.Keyring())
        store = SecretStore(fallback_path=tmp_path / "secrets.toml")
        store.set("claude.access_token", "abc")
        assert store.get("claude.access_token") == "abc"
        assert store.using_fallback is True
        assert (tmp_path / "secrets.toml").exists()

    def test_delete_removes_the_value(self, tmp_path, monkeypatch):
        import keyring
        from keyring.backends import fail

        monkeypatch.setattr(keyring, "get_keyring", lambda: fail.Keyring())
        store = SecretStore(fallback_path=tmp_path / "secrets.toml")
        store.set("codex.access_token", "abc")
        store.delete("codex.access_token")
        assert store.get("codex.access_token") is None


def _snapshot(**kwargs) -> Snapshot:
    base = dict(
        provider="claude",
        status=Status.OK,
        windows=[
            UsageWindow(
                key="claude.5h",
                label_key="window.5h",
                used_pct=48.0,
                resets_at=NOW + timedelta(hours=2),
                window_secs=18_000,
            )
        ],
        plan="max",
    )
    base.update(kwargs)
    return Snapshot(**base)


class TestView:
    def test_rows_carry_localized_labels(self):
        i18n.set_language("ko")
        built = view.build_view(_snapshot(), NOW)
        assert built.rows[0].label == "5시간 세션"
        assert built.rows[0].remaining_text == "52% 남음"

    def test_title_includes_the_plan(self):
        assert view.build_view(_snapshot(), NOW).title == "Claude Code (max)"

    def test_actionable_status_produces_a_message_and_no_rows(self):
        built = view.build_view(_snapshot(status=Status.EXPIRED, windows=[]), NOW)
        assert built.rows == []
        assert "claude" in built.message.lower()

    def test_reset_window_on_stale_data_shows_approximately_zero(self):
        # Rate-limited past a reset: the cached percentage no longer means anything.
        stale = _snapshot(
            status=Status.STALE,
            window_reset_pending=True,
            windows=[
                UsageWindow(
                    key="claude.5h",
                    label_key="window.5h",
                    used_pct=48.0,
                    resets_at=NOW - timedelta(minutes=5),
                    window_secs=18_000,
                )
            ],
        )
        assert view.build_view(stale, NOW).rows[0].remaining_text == "~0%"

    def test_tooltip_fits_the_windows_limit(self):
        views = [view.build_view(_snapshot(), NOW)] * 4
        assert len(view.tooltip(views)) <= 127

    def test_worst_remaining_drives_the_tier(self):
        built = view.build_view(
            _snapshot(
                windows=[
                    UsageWindow("claude.5h", "window.5h", 10.0, NOW + timedelta(hours=1), 18_000),
                    UsageWindow("claude.7d", "window.7d", 95.0, NOW + timedelta(days=3), 604_800),
                ]
            ),
            NOW,
        )
        assert built.worst_remaining == 5
        assert built.tier == "red"
