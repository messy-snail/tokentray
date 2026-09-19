"""Regression coverage for scrolling, disclosure, and bundled typography."""

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
from PySide6.QtWidgets import QDialogButtonBox, QLabel
from shiboken6 import isValid

from tokentray.core import i18n
from tokentray.core.config import Config
from tokentray.core.secrets import SecretStore
from tokentray.notify.webhook import DeliveryResult
from tokentray.ui.fonts import FONT_DIR, initialize_fonts
from tokentray.ui.integration import IntegrationDialog


@pytest.fixture(autouse=True)
def keep_tray_application_alive(qapp):
    previous = qapp.quitOnLastWindowClosed()
    qapp.setQuitOnLastWindowClosed(False)
    yield
    settle(qapp)
    qapp.setQuitOnLastWindowClosed(previous)


@pytest.fixture
def dialog(qapp, tmp_path, monkeypatch):
    initialize_fonts(qapp)
    store = SecretStore(tmp_path / "secrets.toml")
    monkeypatch.setattr(store, "_keyring", lambda: None)
    config = Config({"webhook": {"kind": "slack"}}, tmp_path / "config.toml")
    widget = IntegrationDialog(config, on_saved=lambda _: None, store=store)
    yield widget
    if isValid(widget):
        widget.close()


def settle(qapp):
    for _ in range(12):
        qapp.processEvents()


@pytest.mark.parametrize("language", ["ko", "en"])
@pytest.mark.parametrize("width", [440, 560])
def test_all_services_fit_scrolling_body(qapp, tmp_path, monkeypatch, language, width):
    i18n.set_language(language)
    initialize_fonts(qapp)
    store = SecretStore(tmp_path / "secrets.toml")
    monkeypatch.setattr(store, "_keyring", lambda: None)
    d = IntegrationDialog(Config({}, tmp_path / "config.toml"), on_saved=lambda _: None, store=store)
    d.show()
    d.resize(width, 440)
    assert not d.help.isVisible()
    assert not d.status_scroll.isVisible()
    assert d.buttons.button(QDialogButtonBox.StandardButton.Cancel).text() == i18n.t("integration.cancel")
    for expanded in (False, True):
        d.help_toggle.setChecked(expanded)
        for index in range(4):
            d.kind.setCurrentIndex(index)
            settle(qapp)
            assert d.help.isVisible() == expanded
            assert d.scroll.horizontalScrollBar().maximum() == 0
            for label in d.scroll.findChildren(QLabel):
                if label.isVisible() and label.wordWrap():
                    assert label.height() >= label.heightForWidth(label.width())
            scrollbar = d.scroll.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            settle(qapp)
            notice = d.findChild(QLabel, "webhook-notice")
            bottom = notice.mapTo(d.scroll.viewport(), QPoint(0, notice.height())).y()
            assert bottom <= d.scroll.viewport().height()
            assert d.test_button.geometry().bottom() < d.height()
            assert d.test_button.y() >= d.scroll.geometry().bottom()
            assert d.usage_button.y() == d.test_button.y()
            assert d.test_button.geometry().right() < d.usage_button.x()
            assert d.usage_button.geometry().right() < d.width()
            assert d.buttons.y() > d.usage_button.geometry().bottom()
            assert d.buttons.geometry().bottom() < d.height()
            for button in (d.test_button, d.usage_button):
                assert button.fontMetrics().horizontalAdvance(button.text()) + 24 <= button.width()
    d.close()


def test_status_is_bounded_and_buttons_remain_accessible(dialog, qapp):
    dialog.show()
    dialog.resize(440, 440)
    dialog._show_error("A long error message " * 100)
    settle(qapp)
    assert dialog.status_scroll.isVisible()
    assert dialog.status_scroll.height() <= 80
    assert dialog.status_scroll.verticalScrollBar().maximum() > 0
    assert dialog.test_button.geometry().bottom() < dialog.height()
    dialog._set_status("")
    assert not dialog.status_scroll.isVisible()


def test_test_results_and_cancel(dialog, qapp):
    dialog.show()
    dialog._test()
    assert i18n.t("integration.url_required") in dialog.status.text()
    dialog._set_busy(True)
    dialog._operation_done("test", DeliveryResult(True, 200))
    assert dialog.status.text() == i18n.t("integration.test_ok")
    assert dialog.test_button.isEnabled()
    dialog._operation_done("test", DeliveryResult(False, error="HTTP 500"))
    assert "HTTP 500" in dialog.status.text()
    dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
    assert not dialog.isVisible()


def test_save_uses_existing_persistence(dialog, qtbot):
    saved = []
    dialog._on_saved = saved.append
    dialog.url.setText("https://hooks.slack.com/services/T/B/test")
    dialog.enabled.setChecked(True)
    dialog.show()
    with qtbot.waitSignal(dialog.accepted, timeout=3000):
        dialog._save()
    assert len(saved) == 1
    assert saved[0].enabled and saved[0].kind == "slack"
    assert dialog._config.get("webhook.url") == ""


def test_bundled_font_weights(qapp):
    initialize_fonts(qapp)
    assert qapp.font().family() == "Pretendard"
    for weight in (QFont.Weight.Normal, QFont.Weight.DemiBold, QFont.Weight.Bold):
        font = QFont("Pretendard", 10, weight)
        assert QFontInfo(font).family() == "Pretendard"
        assert QFontInfo(font).weight() == weight
    assert {"Regular", "SemiBold", "Bold"} <= set(QFontDatabase.styles("Pretendard"))
    assert "SIL OPEN FONT LICENSE" in (FONT_DIR / "OFL.txt").read_text()


def test_wrapped_text_shrinks_after_widening(qapp):
    from tokentray.ui.wrapping import WrappingLabel

    label = WrappingLabel("A sentence that needs several lines in a narrow window.")
    label.resize(100, 30)
    label.show()
    settle(qapp)
    narrow_height = label.minimumHeight()
    label.resize(600, 30)
    settle(qapp)
    assert label.minimumHeight() < narrow_height
    label.close()


def test_popup_and_panel_use_bundled_family(qapp):
    from tokentray.ui.panel import DetailPanel
    from tokentray.ui.popup import Toast

    initialize_fonts(qapp)
    widgets = [DetailPanel(on_refresh=lambda: None), Toast(title="tokentray", body="알림 테스트")]
    for widget in widgets:
        widget.ensurePolished()
        for label in widget.findChildren(QLabel):
            label.ensurePolished()
            assert QFontInfo(label.font()).family() == "Pretendard"
        widget.close()


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_font_hinting_is_disabled_only_on_windows(qapp, monkeypatch, platform):
    from tokentray.ui import fonts

    previous = QFont(qapp.font())
    monkeypatch.setattr(fonts.sys, "platform", platform)
    try:
        initialize_fonts(qapp)
        expected = (
            QFont.HintingPreference.PreferNoHinting
            if platform == "win32"
            else QFont.HintingPreference.PreferDefaultHinting
        )
        assert qapp.font().hintingPreference() == expected
    finally:
        qapp.setFont(previous)


def test_widgets_inherit_hinting(qapp, tmp_path):
    from PySide6.QtWidgets import QMenu

    from tokentray.ui.panel import DetailPanel
    from tokentray.ui.popup import Toast

    initialize_fonts(qapp)
    expected = qapp.font().hintingPreference()
    widgets = [
        QMenu(),
        DetailPanel(on_refresh=lambda: None),
        Toast(title="tokentray", body="알림 테스트"),
        IntegrationDialog(
            Config({}, tmp_path / "config.toml"), on_saved=lambda _: None,
            store=SecretStore(tmp_path / "secrets.toml"),
        ),
    ]
    for widget in widgets:
        widget.ensurePolished()
        assert widget.font().hintingPreference() == expected
        for label in widget.findChildren(QLabel):
            label.ensurePolished()
            assert label.font().hintingPreference() == expected
        widget.close()


def test_returning_to_the_saved_service_drops_the_typed_url(qapp, tmp_path, monkeypatch):
    """A Slack URL typed and then abandoned for the saved ntfy was saved as ntfy's."""
    store = SecretStore(tmp_path / "secrets.toml")
    monkeypatch.setattr(store, "_keyring", lambda: None)
    config = Config(
        {"webhook": {"enabled": True, "kind": "ntfy", "configured": True}}, tmp_path / "config.toml"
    )
    d = IntegrationDialog(config, on_saved=lambda _: None, store=store)
    d.kind.setCurrentIndex(d.kind.findData("slack"))
    d.url.setText("https://hooks.slack.com/services/T/B/test")
    d.kind.setCurrentIndex(d.kind.findData("ntfy"))
    assert d.url.text() == ""
    assert d.url.placeholderText() == i18n.t("integration.saved_url")
    d.close()
