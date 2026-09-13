"""Render the README screenshots from synthetic data.

Nothing here reads credentials, touches the network or looks at the real
config: every widget is fed hand-built snapshots against a fixed clock, so the
images are reproducible and carry no account details.

    uv run python scripts/render_screenshots.py                 # en+ko, light+dark
    uv run python scripts/render_screenshots.py --lang ko --theme dark

Rendering is offscreen with the bundled Pretendard font, so the output does not
depend on the desktop it runs on. Times are formatted in UTC where the OS allows
the zone to be pinned (not on Windows).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from tokentray.core import i18n
from tokentray.core.config import Config
from tokentray.core.models import Credits, ExtraUsage, Snapshot, Status, UsageWindow
from tokentray.core.secrets import SecretStore
from tokentray.core.view import PROVIDER_NAMES, build_view
from tokentray.ui import icons, theme
from tokentray.ui.fonts import initialize_fonts
from tokentray.ui.integration import IntegrationDialog
from tokentray.ui.panel import DetailPanel
from tokentray.ui.popup import Toast

NOW = datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc)
RATIO = 2  # device pixels per logical pixel, so the images stay sharp on HiDPI screens
NAMES = ("hero", "login-recovery", "integrations")
HOUR = 3600
DAY = 24 * HOUR

# Used % for (Claude, Codex) in each tray icon of the strip; None means no data.
ICON_STATES = ((38, 22), (71, 47), (86, 64), (None, 47))


def window(key: str, used: float, secs: int, resets_in: timedelta, qualifier: str = "") -> UsageWindow:
    return UsageWindow(key=key, used_pct=used, resets_at=NOW + resets_in, window_secs=secs, qualifier=qualifier)


def snapshot(provider: str, windows=(), *, status: Status = Status.OK, **fields) -> Snapshot:
    return Snapshot(provider=provider, status=status, windows=list(windows), fetched_at=NOW.timestamp(), **fields)


def usage_views() -> list:
    """One busy week: a comfortable 5h window, a 7d window on pace, Opus nearly spent."""
    claude = snapshot("claude", [
        window("claude.5h", 38, 5 * HOUR, timedelta(hours=2, minutes=40)),
        window("claude.7d", 71, 7 * DAY, timedelta(days=2, hours=5)),
        window("claude.7d_opus", 86, 7 * DAY, timedelta(days=2, hours=5), "Opus"),
    ], plan="max", extra=ExtraUsage(enabled=True, used=12.4, limit=50.0))
    codex = snapshot("codex", [
        window("codex.primary", 22, 5 * HOUR, timedelta(hours=4, minutes=10)),
        window("codex.secondary", 47, 7 * DAY, timedelta(days=4, hours=2)),
        window("codex.code_review.primary", 9, 7 * DAY, timedelta(days=4, hours=2), "Code Review"),
    ], plan="pro", credits=Credits(balance=120))
    return [build_view(claude, NOW), build_view(codex, NOW)]


def apply_theme(app: QApplication, dark: bool) -> None:
    """Pin the palette ``theme.is_dark()`` reads, whatever the desktop is set to."""
    colors = theme.DARK if dark else theme.LIGHT
    palette = app.style().standardPalette()
    for role, color in (
        (QPalette.ColorRole.Window, colors.surface),
        (QPalette.ColorRole.WindowText, colors.text),
        (QPalette.ColorRole.Base, colors.surface_alt),
        (QPalette.ColorRole.AlternateBase, colors.surface),
        (QPalette.ColorRole.Text, colors.text),
        (QPalette.ColorRole.Button, colors.surface_alt),
        (QPalette.ColorRole.ButtonText, colors.text),
        (QPalette.ColorRole.PlaceholderText, colors.text_muted),
    ):
        palette.setColor(role, color)
    app.setPalette(palette)


def settle() -> None:
    for _ in range(12):
        QApplication.processEvents()


def grab(widget: QWidget) -> QPixmap:
    pixmap = QPixmap(widget.size() * RATIO)
    pixmap.setDevicePixelRatio(RATIO)
    pixmap.fill(Qt.GlobalColor.transparent)
    widget.render(pixmap)
    return pixmap


def render_icons(dark: bool) -> QPixmap:
    """The tray icon in a few states, side by side on a taskbar-coloured strip."""
    palette = theme.DARK if dark else theme.LIGHT
    size, gap = 64, 24
    width = gap + len(ICON_STATES) * (size + gap)
    strip = QPixmap(QSize(width, size + 2 * gap) * RATIO)
    strip.setDevicePixelRatio(RATIO)
    strip.fill(Qt.GlobalColor.transparent)
    painter = QPainter(strip)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(palette.surface_alt)
        painter.drawRoundedRect(QRect(0, 0, width, size + 2 * gap), 14, 14)
        for index, (claude_used, codex_used) in enumerate(ICON_STATES):
            views = [
                build_view(snapshot("claude", [window("claude.5h", claude_used, 5 * HOUR, timedelta(hours=2))])
                           if claude_used is not None else snapshot("claude", status=Status.NOT_CONFIGURED), NOW),
                build_view(snapshot("codex", [window("codex.primary", codex_used, 5 * HOUR, timedelta(hours=2))]),
                           NOW),
            ]
            target = QRect(gap + index * (size + gap), gap, size, size)
            painter.drawPixmap(target, icons.render_pixmap(views, size * RATIO, palette))
    finally:
        painter.end()
    return strip


def render_panel(views: list, recovery=None) -> DetailPanel:
    panel = DetailPanel(lambda: None)
    panel.recovery = recovery
    panel.update_views(views)
    panel.popup_at(None)
    settle()
    return panel


def render_login_recovery() -> DetailPanel:
    session = SimpleNamespace(waiting=False, message="")
    recovery = SimpleNamespace(
        sessions={"claude": session, "codex": session},
        message=lambda key: i18n.t("connect.hint", provider=PROVIDER_NAMES[key]),
        actions=lambda key: [(i18n.t("connect.login"), lambda: None), (i18n.t("connect.recheck"), lambda: None)],
    )
    views = [build_view(snapshot("claude", status=Status.EXPIRED), NOW), usage_views()[1]]
    return render_panel(views, recovery)


def render_toast() -> Toast:
    """The card a threshold alert raises, built the way ToastManager builds one."""
    row = next(row for row in usage_views()[0].rows if row.key == "claude.7d_opus")
    pace = f"{row.pace} {row.pace_icon}".strip()
    toast = Toast(
        title=i18n.t("fmt.notify_title", provider=PROVIDER_NAMES["claude"]),
        provider="claude",
        body=i18n.t("fmt.notify", label=row.label, pct=row.remaining),
        tier=row.tier,
        fraction=row.remaining / 100,
        detail=" · ".join(part for part in (row.refills, pace) if part),
        sticky=True,
    )
    toast.show()
    settle()
    return toast


def render_integrations(scratch: Path) -> IntegrationDialog:
    store = SecretStore(scratch / "secrets.toml")
    store._keyring = lambda: None  # never ask the real keyring
    config = Config({"webhook": {"enabled": True, "kind": "discord"}}, scratch / "config.toml")
    dialog = IntegrationDialog(config, on_saved=lambda _: None, store=store)
    dialog.show()
    # Tall enough that the notice box needs no scrollbar.
    dialog.resize(560, 580)
    settle()
    return dialog


def render_hero(dark: bool) -> QPixmap:
    """The README's lead image: the panel, an alert card and the tray icons on one backdrop."""
    panel, toast = render_panel(usage_views()), render_toast()
    try:
        panel_shot, toast_shot = grab(panel), grab(toast)
    finally:
        panel.close()
        toast.close()
        settle()
    icon_shot = render_icons(dark)

    def logical(pixmap: QPixmap) -> QSize:
        return pixmap.size() / RATIO

    pad, gap = 24, 8
    panel_size, toast_size, icon_size = logical(panel_shot), logical(toast_shot), logical(icon_shot)
    column = max(toast_size.width(), icon_size.width())
    width = pad + panel_size.width() + gap + column + pad
    height = pad + panel_size.height() + pad

    canvas = QPixmap(QSize(width, height) * RATIO)
    canvas.setDevicePixelRatio(RATIO)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QLinearGradient(QPointF(0, 0), QPointF(width, height))
        stops = ("#1E293B", "#0B1120") if dark else ("#E0E7FF", "#F8FAFC")
        gradient.setColorAt(0.0, QColor(stops[0]))
        gradient.setColorAt(1.0, QColor(stops[1]))
        backdrop = QPainterPath()
        backdrop.addRoundedRect(QRectF(0, 0, width, height), 28, 28)
        painter.fillPath(backdrop, gradient)

        painter.drawPixmap(QPoint(pad, pad), panel_shot)
        # Toast and icons share the right column, centred against the panel's height.
        right = pad + panel_size.width() + gap
        stack = toast_size.height() + 16 + icon_size.height()
        top = pad + (panel_size.height() - stack) // 2
        painter.drawPixmap(QPoint(right + (column - toast_size.width()) // 2, top), toast_shot)
        icons_top = top + toast_size.height() + 16
        painter.drawPixmap(QPoint(right + (column - icon_size.width()) // 2, icons_top), icon_shot)
    finally:
        painter.end()
    return canvas


def render_all(out: Path, language: str, dark: bool) -> list[Path]:
    """Write every README image for one language and theme; return the paths in NAMES order."""
    app = QApplication.instance()
    initialize_fonts(app)
    previous_language, previous_palette = i18n.current_language(), app.palette()
    i18n.set_language(language)
    apply_theme(app, dark)
    out.mkdir(parents=True, exist_ok=True)
    suffix = f"{language}-{'dark' if dark else 'light'}"
    paths = []
    try:
        with tempfile.TemporaryDirectory() as scratch:
            builders = {
                "hero": lambda: render_hero(dark),
                "login-recovery": render_login_recovery,
                "integrations": lambda: render_integrations(Path(scratch)),
            }
            for name in NAMES:
                path = out / f"{name}-{suffix}.png"
                target = builders[name]()
                if isinstance(target, QPixmap):
                    target.save(str(path))
                else:
                    grab(target).save(str(path))
                    target.close()
                    settle()
                paths.append(path)
    finally:
        i18n.set_language(previous_language)
        app.setPalette(previous_palette)
    return paths


def isolate(home: Path) -> None:
    """Point every credential and config lookup at an empty directory."""
    for var in ("HOME", "USERPROFILE", "CLAUDE_CONFIG_DIR", "CODEX_HOME"):
        os.environ[var] = str(home / var.lower())
    for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR"):
        os.environ[var] = str(home / var.lower())
    os.environ["TZ"] = "UTC"
    if hasattr(time, "tzset"):
        time.tzset()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the README screenshots from synthetic data.")
    parser.add_argument("--lang", choices=("en", "ko", "all"), default="all")
    parser.add_argument("--theme", choices=("light", "dark", "all"), default="all")
    parser.add_argument("--out", type=Path, default=Path("docs/images"))
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="tokentray-shots-") as home:
        isolate(Path(home))
        if "QT_QPA_PLATFORM" not in os.environ:
            # A roomy 2x screen: the panel lays itself out against the available
            # height, and logos rasterised at the screen's ratio stay crisp.
            screen = Path(home) / "offscreen.json"
            screen.write_text(json.dumps({"screens": [
                {"name": "shot", "x": 0, "y": 0, "width": 1920, "height": 1200, "logicalDpi": 96, "dpr": RATIO},
            ]}), encoding="utf-8")
            os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={screen}"
        app = QApplication(sys.argv[:1])
        app.setQuitOnLastWindowClosed(False)
        app.setStyle("Fusion")
        languages = ("en", "ko") if args.lang == "all" else (args.lang,)
        themes = (False, True) if args.theme == "all" else (args.theme == "dark",)
        for language in languages:
            for dark in themes:
                for path in render_all(args.out, language, dark):
                    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
