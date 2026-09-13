"""The README screenshot script has to keep working as the widgets change."""

import importlib.util
from pathlib import Path

import pytest
from PySide6.QtGui import QImage, QPalette

from tokentray.core import i18n

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_screenshots.py"


@pytest.fixture(scope="module")
def screenshots():
    spec = importlib.util.spec_from_file_location("render_screenshots", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def keep_alive(qapp):
    previous = qapp.quitOnLastWindowClosed()
    qapp.setQuitOnLastWindowClosed(False)
    yield
    qapp.setQuitOnLastWindowClosed(previous)


@pytest.mark.parametrize(("language", "dark"), [("en", False), ("ko", True)])
def test_renders_every_readme_image(screenshots, qapp, tmp_path, language, dark):
    window = qapp.palette().color(QPalette.ColorRole.Window)

    paths = screenshots.render_all(tmp_path, language, dark)

    theme = "dark" if dark else "light"
    assert [path.name for path in paths] == [f"{name}-{language}-{theme}.png" for name in screenshots.NAMES]
    for path in paths:
        image = QImage(str(path))
        assert not image.isNull()
        assert image.width() > 100 and image.height() > 100
    # Rendering pins a language and a palette; neither may leak into later tests.
    assert i18n.current_language() == "en"
    assert qapp.palette().color(QPalette.ColorRole.Window) == window
