"""Native smoke test with synthetic data; never opens a login or reads credentials.

Run with QT_QPA_PLATFORM=windows and QT_SCALE_FACTOR=1, 1.25 or 1.5.
Artifacts are saved under the ignored build directory.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from tokentray.core import i18n
from tokentray.core.models import Snapshot, Status, UsageWindow
from tokentray.core.view import build_view
from tokentray.ui.fonts import initialize_fonts
from tokentray.ui.panel import DetailPanel
from tokentray.ui.popup import SHADOW_MARGIN, Toast


def main() -> None:
    warnings = []
    qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    initialize_fonts(app)
    i18n.set_language("ko")
    output = Path("build/connection-ui") / os.environ.get("QT_SCALE_FACTOR", "1")
    output.mkdir(parents=True, exist_ok=True)
    panel = DetailPanel(lambda: None)
    session = SimpleNamespace(waiting=False, message="")
    panel.recovery = SimpleNamespace(
        sessions={"claude": session, "codex": session},
        message=lambda key: i18n.t("connect.hint", provider="Claude Code" if key == "claude" else "Codex"),
        actions=lambda key: [(i18n.t("connect.login"), lambda: None), (i18n.t("connect.recheck"), lambda: None)],
    )
    views = [build_view(Snapshot(provider=key, status=Status.EXPIRED)) for key in ("claude", "codex")]
    panel.update_views(views)
    screens = QGuiApplication.screens()
    for index, screen in enumerate(screens):
        area = screen.availableGeometry()
        anchor = QRect(area.right() - 30, area.bottom() - 20, 20, 20)
        for _ in range(5):
            panel.popup_at(anchor)
            QTest.qWait(30)
            panel.update_views(views)
            QTest.qWait(30)
            panel.hide()
        toast = Toast(title="Claude Code", provider="claude", body=i18n.t("connect.expired_message"),
                      actions=[(i18n.t("connect.login"), lambda: panel.popup_at(anchor))])
        toast.activated.connect(lambda: panel.popup_at(anchor))
        toast.present(QPoint(area.right() - toast.width(), area.bottom() - toast.height()), slide_from=24)
        QTest.qWait(250)
        toast.grab().save(str(output / f"toast-{index}.png"))
        QTest.mouseClick(toast, Qt.MouseButton.LeftButton, pos=QPoint(SHADOW_MARGIN + 5, SHADOW_MARGIN + 5))
        QTest.qWait(200)
        assert panel.isVisible()
        panel.grab().save(str(output / f"panel-{index}.png"))
        assert panel.findChildren(QPushButton)
        assert area.contains(panel.geometry())
        panel.hide()
    panel.close()
    verify_refresh(screens, output)
    app.processEvents()
    report = {"platform": app.platformName(), "scale": os.environ.get("QT_SCALE_FACTOR", "1"),
              "screens": len(screens), "warnings": warnings}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))
    assert not any("UpdateLayeredWindow" in message for message in warnings)


def verify_refresh(screens, output: Path) -> None:
    """Exercise native mouse clicks and delayed results without a live provider."""
    for index, screen in enumerate(screens):
        requested = []
        completed = []
        updated = [build_view(Snapshot(provider=key, status=Status.OK, windows=[
            UsageWindow(key=f"{key}.5h", used_pct=27, window_secs=18000,
                        resets_at=datetime.now(timezone.utc) + timedelta(hours=3))
        ])) for key in ("claude", "codex")]
        updated[0].title = "Claude Code (refreshed)"

        def complete() -> None:
            panel.update_views(updated)
            from tokentray.core.refresh import RefreshResult

            panel.refresh_feedback.finish(RefreshResult.from_snapshots([
                Snapshot(provider="claude", status=Status.OK), Snapshot(provider="codex", status=Status.OK),
            ]))
            completed.append(True)

        def request() -> None:
            requested.append(True)
            QTimer.singleShot(100, complete)

        panel = DetailPanel(request)
        panel.update_views(updated)
        corner = screen.availableGeometry().bottomRight()
        anchor = QRect(corner - QPoint(40, 40), corner)
        panel.popup_at(anchor)
        QTest.qWait(50)
        QTest.mouseClick(panel.findChild(QPushButton, "panel-refresh"), Qt.MouseButton.LeftButton)
        assert requested == [True]
        assert panel.isVisible()
        panel.grab().save(str(output / f"refresh-busy-{index}.png"))
        QTest.qWait(700)
        assert completed == [True]
        assert panel.isVisible()
        assert panel.findChild(QPushButton, "panel-refresh").text() == i18n.t("menu.refresh")
        assert panel.findChild(QLabel, "refresh-status").text() == i18n.t("refresh.done")
        panel.grab().save(str(output / f"refresh-done-{index}.png"))
        QTest.qWait(2000)
        assert panel.findChild(QLabel, "refresh-status").text() == ""
        assert any(label.text() == "Claude Code (refreshed)" for label in panel.findChildren(QLabel))
        QTest.mouseClick(panel.findChild(QPushButton, "panel-refresh"), Qt.MouseButton.LeftButton)
        panel.close()
        QTest.qWait(200)
        assert completed == [True, True]
        assert not panel.isVisible()


if __name__ == "__main__":
    main()
