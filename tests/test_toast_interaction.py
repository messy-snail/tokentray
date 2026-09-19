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
