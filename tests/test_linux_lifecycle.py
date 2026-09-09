import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux XDG paths")
def test_stop_acknowledges_before_gui_exits():
    with tempfile.TemporaryDirectory(prefix="tokentray-stop-") as directory:
        root = Path(directory)
        env = os.environ.copy()
        for variable, name in (
            ("XDG_CONFIG_HOME", "config"),
            ("XDG_CACHE_HOME", "cache"),
            ("XDG_STATE_HOME", "state"),
            ("XDG_RUNTIME_DIR", "runtime"),
        ):
            folder = root / name
            folder.mkdir(mode=0o700)
            env[variable] = str(folder)
        env["QT_QPA_PLATFORM"] = "offscreen"
        config = root / "config/tokentray/config.toml"
        config.parent.mkdir()
        config.write_text(
            'native_notifications = false\n'
            '[claude]\nenabled = false\n'
            '[codex]\nenabled = false\n',
            encoding="utf-8",
        )
        command = [sys.executable, "-c", "from tokentray.cli import main; main()"]
        with (root / "gui.log").open("w+") as output:
            process = subprocess.Popen(
                [*command, "--autostart"], env=env, stdout=output, stderr=output
            )
            try:
                socket = root / "runtime/tokentray/tokentray.sock"
                deadline = time.monotonic() + 15
                while not socket.exists() and time.monotonic() < deadline:
                    assert process.poll() is None, "GUI exited before IPC was ready"
                    time.sleep(0.05)
                assert socket.exists(), "GUI did not create its IPC socket"
                result = subprocess.run(
                    [*command, "stop"], env=env, capture_output=True,
                    text=True, timeout=15,
                )
                assert result.returncode == 0, result.stderr
                assert result.stdout.strip() == "stopped"
                assert process.wait(timeout=15) == 0
                assert not socket.exists()
                output.seek(0)
                assert "IPC connection failed" not in output.read()
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
