"""Widget smoke tests.

These run under the offscreen platform plugin, so they prove construction,
signal wiring and painting do not blow up — not that anything looks right. The
visual pass is the manual checklist in MANUAL_TEST.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tokentray.core import i18n  # noqa: E402
from tokentray.core.alerts import AlertEvent  # noqa: E402
from tokentray.core.models import Snapshot, Status, UsageWindow  # noqa: E402
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
                label_key="window.5h",
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
    )


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
        assert i18n.t("menu.quit") in labels
        tray.stop()

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
