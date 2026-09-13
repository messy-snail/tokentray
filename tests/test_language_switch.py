"""Switching language has to rebuild the views, not just repaint them.

``build_view`` bakes translated text into ``ProviderView``/``WindowRow``, so
re-rendering the views the app already holds leaves every label in the old
language while the widgets that call ``t()`` directly flip immediately. On
macOS that mixture stood for a full poll interval.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtCore import Qt

from tokentray.core import i18n
from tokentray.core.models import Snapshot, Status, UsageWindow

NOW_DT = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def snapshot() -> Snapshot:
    return Snapshot(
        provider="claude",
        status=Status.OK,
        plan="max",
        windows=[
            UsageWindow(
                key="claude.5h",
                used_pct=38.0,
                resets_at=NOW_DT + timedelta(seconds=7200),
                window_secs=18_000,
            )
        ],
    )


@pytest.fixture
def controller(qapp, isolated_config):
    from tokentray import app as app_mod
    from tokentray.core.config import Config

    made = app_mod.Controller(qapp, Config({"poll_interval": 120}))
    yield made
    i18n.set_language("en")


def texts(controller) -> str:
    return " ".join(
        part
        for view in controller.views
        for row in view.rows
        for part in (row.label, row.remaining_text, row.refills, row.burns)
        if part
    )


class TestLanguageSwitch:
    def test_the_panel_text_follows_the_new_language(self, controller):
        i18n.set_language("ko")
        controller._update_views([snapshot()])
        assert "남음" in texts(controller)

        controller.set_language("en")
        after = texts(controller)
        assert "remaining" in after
        # The reported symptom: the button said "Refresh now" while the body
        # still read 남음 / 리셋까지 / 소진 예상.
        assert "남음" not in after
        assert "리셋까지" not in after
        assert "소진 예상" not in after

    def test_it_switches_back(self, controller):
        controller._update_views([snapshot()])
        controller.set_language("ko")
        assert "남음" in texts(controller)

    def test_without_a_poll_yet_it_does_not_blank_the_views(self, controller):
        """Nothing has been fetched at first run; rebuilding from nothing would
        replace whatever is on screen with an empty panel."""
        assert controller._snapshots == []
        controller.set_language("ko")
        assert controller.views == []


class TestToastVisibility:
    def test_the_card_stays_up_when_the_app_is_not_frontmost(self, qapp):
        """macOS hides a Qt::Tool NSPanel on deactivation, which is when an
        alert is most worth seeing - and there the card is the only channel."""
        from tokentray.ui.popup import Toast

        toast = Toast(title="t", body="b")
        try:
            assert toast.testAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
            assert toast.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        finally:
            toast.deleteLater()


class TestIntegrationDialogReopens:
    """Closing the settings window used to disable the menu item for good.

    ``IntegrationDialog`` carries ``WA_DeleteOnClose``, so closing it deletes the
    C++ object; the controller kept the wrapper, and the next ``isVisible()``
    raised ``RuntimeError`` from inside the slot - the menu item did nothing and
    said nothing.
    """

    def test_it_opens_again_after_being_closed(self, qapp, controller):
        controller.show_integration_settings()
        dialog = controller._integration_dialog
        assert dialog is not None

        dialog.close()
        # WA_DeleteOnClose defers to deleteLater, so the drop lands on the
        # next turn of the loop - which is all the running app ever gets.
        qapp.processEvents()
        assert controller._integration_dialog is None

        controller.show_integration_settings()
        assert controller._integration_dialog is not None
        controller._integration_dialog.close()

    def test_a_second_request_raises_the_open_one(self, controller):
        controller.show_integration_settings()
        first = controller._integration_dialog
        controller.show_integration_settings()
        assert controller._integration_dialog is first
        first.close()
