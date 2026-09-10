"""Provider identity, compact source labels, and real cached timestamps."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QLabel

from tokentray.core import i18n
from tokentray.core.alerts import AlertEvent
from tokentray.core.models import Snapshot, Status
from tokentray.core.view import build_view
from tokentray.ui import theme
from tokentray.ui.fonts import initialize_fonts
from tokentray.ui.panel import DetailPanel
from tokentray.ui.popup import MAX_VISIBLE, ToastManager
from tokentray.ui.provider_icons import ProviderMark, provider_pixmap

NOW = datetime.fromtimestamp(1073, timezone.utc)


@pytest.fixture(autouse=True)
def keep_alive(qapp):
    initialize_fonts(qapp)
    previous = qapp.quitOnLastWindowClosed()
    qapp.setQuitOnLastWindowClosed(False)
    yield
    for _ in range(5):
        qapp.processEvents()
    qapp.setQuitOnLastWindowClosed(previous)


@pytest.mark.parametrize("language,expected", [("ko", "73초 전 데이터"), ("en", "Data fetched 73 seconds ago")])
def test_source_is_separate_from_diagnostics(language, expected):
    i18n.set_language(language)
    snapshot = Snapshot("claude", Status.CACHED, detail="cached (73s ago)", fetched_at=1000)
    view = build_view(snapshot, NOW)
    assert view.source_status == i18n.t("status.cached")
    assert view.source_tooltip == expected
    assert "cached (73s ago)" in view.source  # Existing non-panel presentation.
    snapshot.status = Status.STALE
    snapshot.detail = "HTTP 500"
    view = build_view(snapshot, NOW)
    assert view.source_status == i18n.t("status.stale")
    assert view.source_tooltip == expected + "\nHTTP 500"


@pytest.mark.parametrize("timestamp", [None, 0, -1, float("nan"), float("inf")])
def test_unknown_fetch_time_has_no_age(timestamp):
    view = build_view(Snapshot("codex", Status.CACHED, fetched_at=timestamp), NOW)
    assert view.source_tooltip == ""


def test_future_time_clamps_to_zero():
    view = build_view(Snapshot("codex", Status.CACHED, fetched_at=2000), NOW)
    assert view.source_tooltip == "Data fetched 0 seconds ago"


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("dpr", [1, 1.25, 1.5, 2])
def test_provider_pixels_and_fallback(dark, dpr):
    pictures = {key: provider_pixmap(key, 16, dpr, dark) for key in ("claude", "codex", None, "unknown")}
    for pixmap in pictures.values():
        assert pixmap.width() == round(16 * dpr)
        assert pixmap.devicePixelRatio() == dpr
        assert not pixmap.isNull()
    assert pictures[None].toImage() == pictures["unknown"].toImage()
    assert pictures["claude"].toImage() != pictures["codex"].toImage()
    image = pictures["codex"].toImage()
    colors = [image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 100]
    assert colors
    assert all(c.red() == (255 if dark else 0) for c in colors)


@pytest.mark.parametrize("language", ["ko", "en"])
@pytest.mark.parametrize("dark", [False, True])
def test_header_stays_on_one_line(qapp, monkeypatch, language, dark):
    i18n.set_language(language)
    monkeypatch.setattr(theme, "current", lambda: theme.DARK if dark else theme.LIGHT)
    monkeypatch.setattr(theme, "is_dark", lambda: dark)
    panel = DetailPanel(lambda: None)
    panel.update_views([build_view(Snapshot(
        provider, status, plan="A very long subscription plan name",
        fetched_at=1000, detail="cached (73s ago)" if status is Status.CACHED else "HTTP 500",
    ), NOW) for provider, status in (("claude", Status.CACHED), ("codex", Status.STALE))])
    panel.popup_at(None)
    for _ in range(10):
        qapp.processEvents()
    titles = panel.findChildren(QLabel, "title")
    sources = [w for w in panel.findChildren(QLabel) if w.property("panel-source")]
    assert [w.provider for w in panel.findChildren(ProviderMark)] == ["claude", "codex"]
    for title, source in zip(titles, sources):
        assert title.text().endswith("…")
        assert "very long" in title.toolTip()
        assert not source.wordWrap()
        assert "cached (" not in source.text()
        assert "73" in source.toolTip()
        assert source.width() >= source.fontMetrics().horizontalAdvance(source.text())
        assert title.mapTo(panel, QPoint(title.width(), 0)).x() + 6 <= source.mapTo(panel, QPoint()).x()
    panel.close()


@pytest.mark.parametrize("providers,expected", [
    (["claude", "codex"], ["claude", "codex"]),
    (["claude"] * (MAX_VISIBLE + 1), ["claude"]),
    (["codex"] * (MAX_VISIBLE + 1), ["codex"]),
    (["claude", "codex"] * (MAX_VISIBLE + 1), [None]),
    ([None], [None]),
])
def test_alert_provider_propagation(monkeypatch, providers, expected):
    manager = ToastManager()
    shown = []
    monkeypatch.setattr(manager, "show", shown.append)
    manager.show_alerts([AlertEvent("info", str(i), "tokentray", "test", provider=provider) for i, provider in enumerate(providers)])
    assert [toast.findChild(ProviderMark).provider for toast in shown] == expected
    for toast in shown:
        toast.close()


def test_test_alerts_use_provider_symbols():
    from tokentray.app import Controller

    shown = []
    controller = SimpleNamespace(toasts=SimpleNamespace(show=shown.append), config=SimpleNamespace(popup_duration=8))
    Controller.show_test_alert(controller)
    assert [toast.findChild(ProviderMark).provider for toast in shown] == ["claude", "codex"]
    for toast in shown:
        toast.close()
