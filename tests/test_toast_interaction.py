"""Toast behaviour that macOS checks found broken: hover and stacked clicks."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent  # noqa: E402

from tokentray.ui import popup  # noqa: E402


@pytest.fixture
def toast(qapp, monkeypatch):
    card = popup.Toast(title="t", body="b", duration=8)
    pointer = {"on_card": False}
    dismissed: list[bool] = []
    monkeypatch.setattr(card, "hovered", lambda: pointer["on_card"])
    monkeypatch.setattr(card, "dismiss", lambda: dismissed.append(True))
    card.pointer = pointer
    card.dismissed = dismissed
    yield card
    card.deleteLater()


class TestHoverWithoutEnterEvents:
    """macOS sends no Enter/Leave to an inactive app, so expiry must look itself."""

    def test_expiry_is_wired_to_the_pointer_check(self, toast):
        toast.present(toast.pos(), slide_from=0)
        assert toast._dismiss.interval() == 8000
        toast._dismiss.timeout.emit()
        assert toast.dismissed == [True]

    def test_a_resting_pointer_holds_the_card(self, toast):
        toast.pointer["on_card"] = True
        toast._expire()
        assert toast.dismissed == []
        assert toast._dismiss.isActive()
        assert toast._dismiss.interval() == popup.HOVER_POLL_MS
        toast._expire()
        assert toast.dismissed == []

    def test_leaving_gives_the_full_wait_again(self, toast):
        toast.pointer["on_card"] = True
        toast._expire()
        toast.pointer["on_card"] = False
        toast._expire()
        assert toast.dismissed == []
        assert toast._dismiss.interval() == 8000
        toast._expire()
        assert toast.dismissed == [True]

    def test_an_untouched_card_expires(self, toast):
        toast._expire()
        assert toast.dismissed == [True]

    def test_a_leave_event_after_a_hold_does_not_add_a_second_wait(self, toast):
        # When tokentray is frontmost both paths run; the wait must not double.
        toast.pointer["on_card"] = True
        toast._expire()
        toast.pointer["on_card"] = False
        toast.leaveEvent(QEvent(QEvent.Type.Leave))
        assert toast._dismiss.interval() == 8000
        toast._expire()
        assert toast.dismissed == [True]


class TestStackedClicks:
    """A card's transparent shadow margin overlaps its neighbour in a stack.

    Bottom-up, the upper card's margin lay over the lower card's x, so pressing
    it closed the upper card and opened the panel instead.
    """

    @pytest.fixture
    def stack(self, qapp):
        from PySide6.QtWidgets import QPushButton

        manager = popup.ToastManager(duration=8, position="bottom-right")
        activated: list[str] = []
        manager.on_activated = lambda: activated.append("panel")
        lower = popup.Toast(title="lower", body="b", duration=8)
        upper = popup.Toast(title="upper", body="b", duration=8)
        manager.show(lower)
        manager.show(upper)
        yield manager, lower, upper, lower.findChild(QPushButton, "close"), activated
        for toast in (lower, upper):
            toast.deleteLater()

    @staticmethod
    def release(toast, global_point):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        local = toast.mapFromGlobal(global_point)
        toast.mouseReleaseEvent(QMouseEvent(
            QEvent.Type.MouseButtonRelease, QPointF(local), QPointF(global_point),
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        ))

    @staticmethod
    def dismissing(toast) -> bool:
        return toast._fade.endValue() == 0.0

    def test_lower_cards_close_button_reaches_the_lower_card(self, stack):
        _, lower, upper, close, activated = stack
        x = close.mapToGlobal(close.rect().center())
        assert not upper.card_contains(x)
        self.release(upper, x)
        assert self.dismissing(lower)
        assert not self.dismissing(upper)
        assert activated == []

    def test_body_under_a_margin_opens_that_card(self, stack):
        _, lower, upper, _, activated = stack
        body = lower.mapToGlobal(lower._card.geometry().center())
        self.release(upper, body)
        assert self.dismissing(lower) and not self.dismissing(upper)
        assert activated == ["panel"]

    def test_empty_margin_does_nothing(self, stack):
        _, lower, upper, _, activated = stack
        corner = upper.mapToGlobal(upper.rect().topLeft()) + popup.QPoint(2, 2)
        assert not lower.card_contains(corner) and not upper.card_contains(corner)
        self.release(upper, corner)
        assert not self.dismissing(lower) and not self.dismissing(upper)
        assert activated == []

    def test_own_card_click_still_opens_the_panel(self, stack):
        _, lower, upper, _, activated = stack
        self.release(upper, upper.mapToGlobal(upper._card.geometry().center()))
        assert self.dismissing(upper) and not self.dismissing(lower)
        assert activated == ["panel"]


class TestDismissIsIdempotent:
    """One gesture can ask a card to go twice.

    An action button dismisses the card, and the release that pressed it also
    reads as a click on the card. ``dismiss`` restarted the fade from wherever
    it had got to and connected ``finished`` to ``close`` again each time, so a
    card asked twice took longer to leave than one asked once.
    """

    def test_a_second_dismiss_does_not_restart_the_fade(self, qapp, monkeypatch):
        card = popup.Toast(title="t", body="b", duration=8)
        card.present(card.pos(), slide_from=0)
        fades: list[float] = []
        real = card._animate_opacity
        monkeypatch.setattr(
            card, "_animate_opacity", lambda value, ms: (fades.append(value), real(value, ms))
        )

        card.dismiss()
        card.dismiss()

        # One fade-out, so one ``finished``, so one ``close``.
        assert fades == [0.0]
        card.deleteLater()


class TestShutdownTakesCardsOffScreen:
    """``clear`` at quit cannot wait for a fade the event loop will outlive."""

    def test_immediate_clear_closes_rather_than_fades(self, qapp):
        manager = popup.ToastManager(duration=8)
        manager.show(popup.Toast(title="t", body="b", duration=8))
        assert manager._toasts

        manager.clear(immediate=True)

        assert manager._toasts == []
