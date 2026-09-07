# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build.

One-dir, not one-file: a one-file build unpacks Qt to a temp directory on every
launch, which for a program that starts at login and then sits idle is a second
of start-up cost and an antivirus scan for no benefit.

Windows gets two executables from one collection - a console `tokentray` for the
CLI and a windowed `tokentray-gui` that autostart uses - so logging in never
flashes a console window.
"""

import sys
from pathlib import Path

BUILD = Path(SPECPATH)
ROOT = BUILD.parent
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

# keyring finds its backends by dynamic import, so PyInstaller cannot see them.
HIDDEN = [
    "keyring.backends.chainer",
    "keyring.backends.fail",
    "keyring.backends.null",
]
if IS_WINDOWS:
    HIDDEN.append("keyring.backends.Windows")
elif IS_MACOS:
    HIDDEN.append("keyring.backends.macOS")
else:
    HIDDEN += ["keyring.backends.SecretService", "keyring.backends.kwallet"]

# Qt ships far more than a tray app needs; dropping these roughly halves the
# bundle. QtNetwork stays: QLocalServer/QLocalSocket carry the IPC channel.
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtQml",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSerialPort",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
    "tkinter", "unittest", "pydoc_data",
]

common = dict(
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

# Excluding the Python bindings above does not drop the Qt shared libraries:
# PySide6's hook collects those as binaries, so they survive as dead weight.
# Nothing here is linked from QtCore/QtGui/QtWidgets/QtNetwork, which is all we use.
DROP_LIBS = (
    "Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt63D", "Qt6WebEngine", "Qt6Multimedia",
    "Qt6Charts", "Qt6DataVisualization", "Qt6Designer", "Qt6Test", "Qt6Sql",
    "Qt6Bluetooth", "Qt6Nfc", "Qt6Positioning", "Qt6Location", "Qt6SerialPort",
    "Qt6Help", "Qt6Spatial", "Qt6ShaderTools", "Qt6VirtualKeyboard",
    "libQt6Quick", "libQt6Qml", "libQt6Pdf", "libQt63D", "libQt6WebEngine",
    "libQt6Multimedia", "libQt6Charts", "libQt6DataVisualization",
    "libQt6Designer", "libQt6Test", "libQt6Sql", "libQt6Bluetooth",
    "libQt6Nfc", "libQt6Positioning", "libQt6Location", "libQt6SerialPort",
    "libQt6Help", "libQt6ShaderTools", "libQt6VirtualKeyboard",
)


def prune(binaries):
    """Drop Qt libraries this app never loads.

    opengl32sw is deliberately kept: it is the software renderer Qt falls back to
    with no GPU driver, which is exactly the VM and remote-desktop case where a
    missing renderer would leave the user with no window at all.
    """
    return [b for b in binaries if not Path(b[0]).name.startswith(DROP_LIBS)]


gui_analysis = Analysis([str(BUILD / "entry_gui.py")], **common)
gui_analysis.binaries = prune(gui_analysis.binaries)
gui_pyz = PYZ(gui_analysis.pure)

ICON = None
for candidate in (ROOT / "src/tokentray/resources/tokentray.ico",
                  ROOT / "src/tokentray/resources/tokentray.icns"):
    if candidate.exists():
        ICON = str(candidate)
        break

gui_exe = EXE(
    gui_pyz,
    gui_analysis.scripts,
    [],
    exclude_binaries=True,
    name="tokentray-gui",
    console=False,          # no console window when the OS starts it at login
    icon=ICON,
    disable_windowed_traceback=False,
)

outputs = [gui_exe, gui_analysis.binaries, gui_analysis.datas]

if IS_WINDOWS:
    # A second, console-attached executable for `tokentray status` and friends.
    cli_analysis = Analysis([str(BUILD / "entry_cli.py")], **common)
    cli_analysis.binaries = prune(cli_analysis.binaries)
    cli_pyz = PYZ(cli_analysis.pure)
    cli_exe = EXE(
        cli_pyz,
        cli_analysis.scripts,
        [],
        exclude_binaries=True,
        name="tokentray",
        console=True,
        icon=ICON,
    )
    outputs = [gui_exe, cli_exe,
               gui_analysis.binaries, gui_analysis.datas,
               cli_analysis.binaries, cli_analysis.datas]

coll = COLLECT(*outputs, strip=False, upx=False, name="tokentray")

if IS_MACOS:
    app = BUNDLE(
        coll,
        name="tokentray.app",
        icon=ICON,
        bundle_identifier="io.github.messy-snail.tokentray",
        info_plist={
            # Menu-bar only: no Dock icon, no app switcher entry.
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
        },
    )
