"""Widget smoke tests.

These run under the offscreen platform plugin, so they prove construction,
signal wiring and painting do not blow up — not that anything looks right. The
visual pass is the manual checklist in MANUAL_TEST.md.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from tokentray.core import i18n  # noqa: E402
from tokentray.core.compute import TIER_COLORS  # noqa: E402
from tokentray.core.alerts import AlertEvent  # noqa: E402
from tokentray.core.config import Config  # noqa: E402
from tokentray.core.models import Snapshot, Status, UsageWindow  # noqa: E402
from tokentray.core.secrets import SecretStore  # noqa: E402
from tokentray.core.view import build_view  # noqa: E402
from tokentray.ui import icons, popup, theme  # noqa: E402

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def make_view(provider="claude", used=48.0, status=Status.OK, key="claude.5h"):
    windows = (
        [
            UsageWindow(
                key=key,
                used_pct=used,
                resets_at=NOW + timedelta(hours=2),
                window_secs=18_000,
            )
        ]
        if status.has_data
        else []
    )
    return build_view(Snapshot(provider=provider, status=status, windows=windows), NOW)


def make_event(remaining=25, tier="orange", priority="high"):
    view = make_view(used=100 - remaining)
    return AlertEvent(
        kind="threshold",
        key=view.rows[0].key,
        title="t",
        body="b",
        tier=tier,
        priority=priority,
        row=view.rows[0],
        provider="claude",
    )


# Pixel probes run at 64px: at tray sizes a ring is only a couple of pixels wide,
# so antialiasing blends the sample with whatever is next to it.
PROBE_SIZE = 64


def probe(pixmap, radius, degrees, size=PROBE_SIZE):
    """The colour `radius` px from the centre, `degrees` clockwise from 12 o'clock."""
    centre = size / 2.0
    x = centre + radius * math.sin(math.radians(degrees))
    y = centre - radius * math.cos(math.radians(degrees))
    return pixmap.toImage().pixelColor(int(x), int(y))


def assert_tier(color, tier):
    want = QColor(TIER_COLORS[tier])
    assert color.alpha() > 200, f"expected opaque {tier}, got {color.name()}"
    for got, expected in zip(
        (color.red(), color.green(), color.blue()),
        (want.red(), want.green(), want.blue()),
    ):
        assert abs(got - expected) <= 6, f"expected {tier}, got {color.name()}"


def assert_track(color):
    # Translucent in both themes - light is 15% black, dark 13% white.
    assert 0 < color.alpha() < 80, f"expected the track, got alpha {color.alpha()}"


def assert_empty(color):
    assert color.alpha() == 0, f"expected nothing drawn, got {color.name()}"


class TestRingGeometry:
    """Layout arithmetic, checked without a painter."""

    @pytest.mark.parametrize("size", icons.ICON_SIZES + (128, 256, 512, 1024))
    def test_single_ring_matches_the_legacy_geometry(self, size):
        # The packaged .icns/.ico/.png are rendered from this code, so a lone
        # ring has to keep the exact geometry it shipped with or every asset
        # silently changes underneath the bundle.
        stroke = size * 0.17
        band = icons.ring_bands(size, 1)[0]
        assert band.stroke == pytest.approx(stroke)
        assert band.radius == pytest.approx(
            size / 2 - max(1.0, size * 0.06) - stroke / 2
        )

    @pytest.mark.parametrize("size", icons.ICON_SIZES + (128, 256, 512, 1024))
    @pytest.mark.parametrize("count", range(1, icons.MAX_RINGS + 1))
    def test_rings_fit_inside_the_pixmap(self, size, count):
        bands = icons.ring_bands(size, count)
        assert bands[0].radius + bands[0].stroke / 2 <= size / 2 + 1e-9
        assert bands[-1].radius - bands[-1].stroke / 2 >= -1e-9

    @pytest.mark.parametrize("size", icons.ICON_SIZES)
    @pytest.mark.parametrize("count", range(2, icons.MAX_RINGS + 1))
    def test_rings_never_overlap(self, size, count):
        bands = icons.ring_bands(size, count)
        for outer, inner in zip(bands, bands[1:]):
            clearance = (outer.radius - outer.stroke / 2) - (
                inner.radius + inner.stroke / 2
            )
            assert clearance >= icons._MIN_GAP - 1e-9

    def test_strokes_stay_legible_at_sixteen(self):
        # 16px is the smallest tray slot; below ~1.6px a ring antialiases away.
        assert all(band.stroke >= 1.6 for band in icons.ring_bands(16, 2))

    def test_ring_count_is_capped(self):
        assert len(icons.ring_bands(64, 9)) == icons.MAX_RINGS

    def test_zero_providers_still_gets_one_band(self):
        assert len(icons.ring_bands(16, 0)) == 1

    @pytest.mark.parametrize("count", range(1, icons.MAX_RINGS + 1))
    def test_stroke_grows_with_size(self, count):
        strokes = [icons.ring_bands(s, count)[0].stroke for s in icons.ICON_SIZES]
        assert strokes == sorted(strokes)


class TestIcons:
    @pytest.mark.parametrize("size", icons.ICON_SIZES)
    def test_every_size_renders(self, qapp, size):
        pixmap = icons.render_pixmap([make_view()], size)
        assert not pixmap.isNull()
        assert pixmap.size().width() == size

    def test_icon_carries_all_sizes(self, qapp):
        icon = icons.build_icon([make_view()])
        assert {s.width() for s in icon.availableSizes()} >= set(icons.ICON_SIZES)

    def test_two_providers_render_without_data_for_one(self, qapp):
        views = [make_view(), make_view(provider="codex", status=Status.NOT_CONFIGURED)]
        assert not icons.render_pixmap(views, 16).isNull()

    def test_no_providers_still_produces_an_icon(self, qapp):
        # An empty tray slot reads as a crash; something must always be drawn.
        assert not icons.render_pixmap([], 16).isNull()

    def test_exhausted_window_renders(self, qapp):
        assert not icons.render_pixmap([make_view(used=100.0)], 16).isNull()

    def test_two_providers_paint_two_distinct_rings(self, qapp):
        # Claude 80% (green) outside, Codex 30% (orange) inside. Two providers
        # at the same tier used to merge into one unbroken ring; separate radii
        # and separate sweeps are what stops that.
        views = [make_view(used=20.0), make_view(provider="codex", used=70.0)]
        pixmap = icons.render_pixmap(views, PROBE_SIZE)
        outer, inner = icons.ring_bands(PROBE_SIZE, 2)

        assert_tier(probe(pixmap, outer.radius, 45), "green")
        assert_tier(probe(pixmap, inner.radius, 45), "orange")
        assert_tier(probe(pixmap, outer.radius, 180), "green")  # 80% reaches past 6
        assert_track(probe(pixmap, inner.radius, 180))          # 30% does not
        assert_track(probe(pixmap, outer.radius, 300))
        assert_track(probe(pixmap, inner.radius, 300))

    def test_dataless_provider_keeps_its_ring_slot(self, qapp):
        # Filtering the empty provider out would move the other one, so the same
        # arc length would mean a different number from one poll to the next.
        inner = icons.ring_bands(PROBE_SIZE, 2)[1]
        alone = icons.render_pixmap([make_view()], PROBE_SIZE)
        paired = icons.render_pixmap(
            [make_view(), make_view(provider="codex", status=Status.NOT_CONFIGURED)],
            PROBE_SIZE,
        )
        assert_empty(probe(alone, inner.radius, 45))
        assert_track(probe(paired, inner.radius, 45))

    def test_single_provider_uses_the_full_outer_ring(self, qapp):
        pixmap = icons.render_pixmap([make_view(used=20.0)], PROBE_SIZE)
        band = icons.ring_bands(PROBE_SIZE, 1)[0]
        assert_tier(probe(pixmap, band.radius, 45), "green")
        assert_track(probe(pixmap, band.radius, 300))
        assert_empty(probe(pixmap, 3, 45))  # the hole stays a hole

    def test_arc_drains_clockwise_from_twelve(self, qapp):
        pixmap = icons.render_pixmap([make_view(used=50.0)], PROBE_SIZE)
        band = icons.ring_bands(PROBE_SIZE, 1)[0]
        for filled in (10, 170):
            assert_tier(probe(pixmap, band.radius, filled), "orange")
        for drained in (190, 350):
            assert_track(probe(pixmap, band.radius, drained))

    def test_full_quota_fills_the_whole_ring(self, qapp):
        views = [make_view(used=0.0), make_view(provider="codex", used=0.0)]
        pixmap = icons.render_pixmap(views, PROBE_SIZE)
        for band in icons.ring_bands(PROBE_SIZE, 2):
            for degrees in (5, 90, 180, 270, 355):
                assert_tier(probe(pixmap, band.radius, degrees), "green")

    def test_exhausted_ring_is_distinguishable_from_no_data(self, qapp):
        # Nothing left and never configured both leave a bare track otherwise,
        # and they want opposite reactions from the user.
        pixmap = icons.render_pixmap([make_view(used=100.0)], PROBE_SIZE)
        band = icons.ring_bands(PROBE_SIZE, 1)[0]
        assert_tier(probe(pixmap, band.radius, 2), "red")
        assert_track(probe(pixmap, band.radius, 45))

    def test_no_data_anywhere_still_shows_the_idle_tick(self, qapp):
        views = [
            make_view(status=Status.NOT_CONFIGURED),
            make_view(provider="codex", status=Status.NOT_CONFIGURED),
        ]
        pixmap = icons.render_pixmap(views, PROBE_SIZE)
        outer, inner = icons.ring_bands(PROBE_SIZE, 2)

        tick = probe(pixmap, outer.radius, 10)
        assert tick.alpha() > 200
        channels = (tick.red(), tick.green(), tick.blue())
        assert max(channels) - min(channels) <= 20  # muted grey, not a tier colour
        assert_track(probe(pixmap, inner.radius, 10))

    def test_retina_request_lands_on_an_exact_raster(self, qapp):
        # 22pt at 2x is 44 physical pixels. Without that exact size in the set,
        # Qt downsamples the 48px raster and blurs the gap between the rings.
        assert 44 in icons.ICON_SIZES
        views = [make_view(), make_view(provider="codex", used=70.0)]
        got = icons.build_icon(views).pixmap(QSize(22, 22), 2.0)
        assert got.width() == 44
        assert got.devicePixelRatio() == 2.0
        assert got.toImage() == icons.render_pixmap(views, 44).toImage()


class TestTheme:
    def test_palettes_define_every_tier(self, qapp):
        for palette in (theme.LIGHT, theme.DARK):
            for tier in ("green", "orange", "red"):
                assert palette.tier(tier).isValid()

    def test_current_returns_a_palette(self, qapp):
        assert theme.current() in (theme.LIGHT, theme.DARK)


class TestToast:
    def test_constructs_and_closes(self, qapp):
        toast = popup.Toast(title="t", body="b", fraction=0.5, detail="d")
        assert toast.width() > 0
        mark = toast.findChild(QLabel, "app-icon")
        assert mark is not None and mark.pixmap() is not None
        toast.close()

    def test_does_not_take_focus(self, qapp):
        from PySide6.QtCore import Qt

        toast = popup.Toast(title="t", body="b")
        # Stealing focus from whatever the user is typing in is the fastest way
        # to get a notification tool uninstalled.
        assert toast.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        assert toast.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        assert toast.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        toast.close()

    def test_sticky_toast_has_no_dismiss_timer(self, qapp):
        toast = popup.Toast(title="t", body="b", sticky=True)
        toast.present(toast.pos(), slide_from=0)
        assert not toast._dismiss.isActive()
        toast.close()

    def test_action_buttons_are_built(self, qapp):
        from PySide6.QtWidgets import QPushButton

        calls = []
        toast = popup.Toast(
            title="t", body="b", sticky=True, actions=[("Got it", lambda: calls.append(1))]
        )
        buttons = [b for b in toast.findChildren(QPushButton) if b.text() == "Got it"]
        assert len(buttons) == 1
        buttons[0].click()
        assert calls == [1]
        toast.close()


class TestToastManager:
    def test_shows_one_card_per_event(self, qapp):
        manager = popup.ToastManager()
        manager.show_alerts([make_event(), make_event(remaining=10)])
        assert len(manager._toasts) == 2
        manager.clear()

    def test_a_burst_collapses_into_one_summary(self, qapp):
        # Four windows crossing at once is one situation, not four notifications.
        manager = popup.ToastManager()
        manager.show_alerts([make_event() for _ in range(4)])
        assert len(manager._toasts) == 1
        manager.clear()

    def test_empty_list_shows_nothing(self, qapp):
        manager = popup.ToastManager()
        manager.show_alerts([])
        assert manager._toasts == []

    def test_stacked_toasts_do_not_overlap(self, qapp):
        manager = popup.ToastManager()
        manager.show_alerts([make_event(), make_event(remaining=10)])
        first, second = manager._toasts
        assert first.pos() != second.pos()
        manager.clear()


class TestTray:
    def test_menu_covers_every_action(self, qapp):
        from tokentray.ui.tray import Tray

        i18n.set_language("en")
        tray = Tray()
        labels = [a.text() for a in tray._menu.actions() if a.text()]
        assert i18n.t("menu.open_panel") in labels
        assert i18n.t("menu.integration") in labels
        assert i18n.t("menu.quit") in labels
        tray.stop()

    def test_integration_dialog_exposes_one_destination(self, qapp, tmp_path, monkeypatch):
        from tokentray.ui.integration import IntegrationDialog

        config = Config({}, tmp_path / "config.toml")
        store = SecretStore(tmp_path / "secrets.toml")
        monkeypatch.setattr(store, "_keyring", lambda: None)
        dialog = IntegrationDialog(config, on_saved=lambda _settings: None, store=store)
        assert dialog.kind.count() == 4
        assert dialog.url.echoMode() == dialog.url.EchoMode.Password
        dialog.close()

    def test_integration_dialog_guides_every_service(self, qapp, tmp_path, monkeypatch):
        from tokentray.ui.integration import IntegrationDialog

        config = Config({}, tmp_path / "config.toml")
        store = SecretStore(tmp_path / "secrets.toml")
        monkeypatch.setattr(store, "_keyring", lambda: None)
        dialog = IntegrationDialog(config, on_saved=lambda _settings: None, store=store)
        steps = dialog.findChild(QLabel, "webhook-steps")
        shape = dialog.findChild(QLabel, "webhook-url-shape")
        assert steps is not None and shape is not None

        seen = set()
        for index in range(dialog.kind.count()):
            dialog.kind.setCurrentIndex(index)
            kind = str(dialog.kind.currentData())
            # Every service gets real steps, not a fallback or a raw i18n key.
            assert "<ol>" in steps.text() and "integration.steps" not in steps.text()
            seen.add(steps.text())
            # A generic webhook has no fixed URL shape, so that line goes away.
            assert shape.isVisibleTo(dialog) is (kind != "generic")
            if kind == "slack":
                assert "hooks.slack.com/services/" in shape.text()
            if kind == "discord":
                # <id> must survive: as rich text Qt would eat it as a tag.
                assert "<id>" in shape.text()
                assert shape.textFormat() == Qt.TextFormat.PlainText
        assert len(seen) == dialog.kind.count(), "two services share one set of steps"
        dialog.close()

    def test_retranslate_rebuilds_in_the_new_language(self, qapp):
        from tokentray.ui.tray import Tray

        tray = Tray()
        i18n.set_language("ko")
        tray.retranslate()
        labels = [a.text() for a in tray._menu.actions() if a.text()]
        assert i18n.t("menu.quit") in labels
        i18n.set_language("en")
        tray.stop()

    def test_tooltip_reflects_current_data(self, qapp):
        from tokentray.ui.tray import Tray

        tray = Tray()
        tray.update_views([make_view()])
        assert "CC" in tray._icon.toolTip()
        tray.stop()


class TestPanel:
    def test_builds_for_mixed_provider_states(self, qapp):
        from tokentray.ui.panel import DetailPanel

        panel = DetailPanel(on_refresh=lambda: None)
        panel.update_views(
            [make_view(), make_view(provider="codex", status=Status.EXPIRED)]
        )
        panel._rebuild()
        assert panel.width() > 0
        panel.close()

    def test_survives_repeated_rebuilds(self, qapp):
        # The panel is rebuilt on every poll; leaked child widgets would pile up.
        from tokentray.ui.panel import DetailPanel

        panel = DetailPanel(on_refresh=lambda: None)
        for _ in range(5):
            panel.update_views([make_view()])
            panel._rebuild()
        panel.close()
