"""Tests for the code that differs by operating system.

Almost nothing here is skipped by platform. The point of a three-OS CI matrix is
lost if each runner only exercises its own branch, so the backends are driven
through injected paths and stubbed system calls instead - a macOS runner proves
the Windows registry logic and vice versa. Only the handful of tests that call a
real OS API (``CommandLineToArgvW``, POSIX file modes) are gated.
"""

from __future__ import annotations

import os
import pathlib
import stat
import sys
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QThread  # noqa: E402

from tokentray import autostart, ipc  # noqa: E402
from tokentray.core import paths  # noqa: E402
from tokentray.core.config import Config  # noqa: E402
from tokentray.core.models import Snapshot, Status  # noqa: E402

COMMAND = ["/opt/tokentray/tokentray-gui"]


class StubProvider:
    """Stands in for a real provider so a poll never touches the network."""

    def __init__(self, provider: str = "claude") -> None:
        self._snapshot = Snapshot(provider=provider, status=Status.OK)
        self.closed = False

    def fetch(self, force: bool = False) -> Snapshot:
        return self._snapshot

    def close(self) -> None:
        self.closed = True


class TestPollThreadNeverTouchesWidgets:
    """The poller produces data; only the main thread may render it.

    This is not a style preference. Qt requires widget work on the GUI thread on
    every platform, and macOS enforces it fatally: AppKit aborts the process the
    moment it is asked to build an NSWindow anywhere else, which is what a toast
    does. Qt can only queue a cross-thread signal onto the main thread if the
    receiver is a QObject with an affinity to queue onto - a plain Python
    receiver has none, and the slot then runs on the emitting thread.
    """

    def test_controller_is_bound_to_the_main_thread(self, qapp, isolated_config):
        from tokentray import app as app_mod

        controller = app_mod.Controller(qapp, Config({"poll_interval": 120}))
        assert controller.thread() is qapp.thread()

    def test_snapshots_are_rendered_on_the_main_thread(
        self, qapp, isolated_config, monkeypatch
    ):
        from tokentray import app as app_mod

        controller = app_mod.Controller(qapp, Config({"poll_interval": 120}))
        controller._worker._providers = [StubProvider()]

        seen: dict[str, QThread] = {}
        real_build_view = app_mod.build_view

        def spy(snapshot, now):
            seen.setdefault("thread", QThread.currentThread())
            return real_build_view(snapshot, now)

        monkeypatch.setattr(app_mod, "build_view", spy)

        controller._thread.start()
        try:
            controller.refresh(force=False)
            deadline = time.monotonic() + 10
            while "thread" not in seen and time.monotonic() < deadline:
                qapp.processEvents()
            assert "thread" in seen, "the poll thread never delivered a snapshot"
            assert seen["thread"] is qapp.thread()
        finally:
            controller._thread.quit()
            controller._thread.wait(3000)


class TestWelcomeToast:
    """A tray icon nobody can find is the same as no tray icon.

    Both Windows and macOS can swallow a brand new item - the overflow flyout
    there, a menu bar manager here - so the one-time welcome has to say so.
    """

    @pytest.fixture
    def captured(self, qapp, isolated_config, monkeypatch):
        from tokentray import app as app_mod
        from tokentray.ui import popup

        controller = app_mod.Controller(qapp, Config({"poll_interval": 120}))
        recorded: dict = {}
        # Record the arguments rather than build a real card: this is about what
        # the welcome says, not how it draws.
        monkeypatch.setattr(popup, "Toast", lambda **kw: recorded.update(kw) or kw)
        monkeypatch.setattr(controller.toasts, "show", lambda toast: None)
        monkeypatch.setattr(controller.dispatcher, "notify_native", lambda *args: None)

        def build(platform: str) -> dict:
            monkeypatch.setattr(sys, "platform", platform)
            controller._show_welcome()
            return recorded

        return build

    def test_macos_points_at_menu_bar_managers(self, captured):
        toast = captured("darwin")
        assert "Bartender" in toast["detail"]
        # There is no settings URL to offer: the manager is somebody else's app.
        assert [label for label, _ in toast["actions"]] == ["Got it"]

    def test_windows_offers_the_tray_settings_shortcut(self, captured):
        toast = captured("win32")
        assert toast["detail"] == ""
        assert [label for label, _ in toast["actions"]] == ["Open tray settings", "Got it"]

    def test_linux_needs_neither(self, captured):
        toast = captured("linux")
        assert toast["detail"] == ""
        assert [label for label, _ in toast["actions"]] == ["Got it"]


class TestGuiCommand:
    """What each OS is asked to run at login."""

    def test_frozen_build_prefers_the_sibling_gui_executable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "tokentray"))
        sibling = tmp_path / (
            f"{autostart.ENTRY}.exe" if os.name == "nt" else autostart.ENTRY
        )
        sibling.write_text("", encoding="utf-8")
        assert autostart.gui_command() == [str(sibling)]

    def test_frozen_build_falls_back_to_itself(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "tokentray"))
        assert autostart.gui_command() == [str(tmp_path / "tokentray")]

    def test_an_installed_shim_wins_over_the_interpreter(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.setattr(autostart.shutil, "which", lambda name: "/usr/local/bin/" + name)
        assert autostart.gui_command() == ["/usr/local/bin/tokentray-gui"]

    def test_development_checkout_runs_the_module(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.setattr(autostart.shutil, "which", lambda name: None)
        # Swap the module's reference rather than os.name itself, which is read
        # by half the standard library.
        monkeypatch.setattr(autostart, "os", SimpleNamespace(name="posix"))
        assert autostart.gui_command() == [sys.executable, "-m", "tokentray"]

    def test_windows_prefers_pythonw_so_no_console_flashes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.setattr(autostart.shutil, "which", lambda name: None)
        monkeypatch.setattr(autostart, "os", SimpleNamespace(name="nt"))
        monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
        pythonw = tmp_path / "pythonw.exe"
        pythonw.write_text("", encoding="utf-8")
        assert autostart.gui_command() == [str(pythonw), "-m", "tokentray"]


class TestLinuxAutostart:
    """XDG desktop entry. Pure pathlib and shlex, so it runs on any OS."""

    @pytest.fixture
    def entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        return tmp_path / "autostart" / "tokentray.desktop"

    def test_enable_writes_an_entry_that_round_trips(self, entry):
        from tokentray.autostart import linux

        assert linux.is_enabled() is False
        linux.enable(COMMAND)
        assert linux.is_enabled() is True
        assert linux.registered_command() == COMMAND

    def test_the_entry_marks_itself_as_an_autostart_launch(self, entry):
        from tokentray.autostart import linux

        linux.enable(COMMAND)
        text = entry.read_text(encoding="utf-8")
        assert "--autostart" in text
        # GNOME needs both keys: one to honour the entry, one to let the tray
        # host come up before the app looks for it.
        assert "X-GNOME-Autostart-enabled=true" in text
        assert "X-GNOME-Autostart-Delay=10" in text
        # Without a named icon, GNOME's Startup Applications list shows a
        # generic placeholder for the entry.
        assert "Icon=io.github.messy-snail.tokentray" in text

    def test_a_command_with_spaces_survives_the_round_trip(self, entry):
        from tokentray.autostart import linux

        spaced = ["/home/a b/tokentray-gui"]
        linux.enable(spaced)
        assert linux.registered_command() == spaced

    def test_disable_removes_the_entry_and_is_idempotent(self, entry):
        from tokentray.autostart import linux

        linux.enable(COMMAND)
        linux.disable()
        linux.disable()
        assert linux.is_enabled() is False
        assert linux.registered_command() is None


class TestMacosAutostart:
    """LaunchAgent plist. plistlib is portable; launchctl is stubbed."""

    @pytest.fixture
    def calls(self, tmp_path, monkeypatch):
        from tokentray.autostart import macos

        recorded: list[tuple[str, ...]] = []
        monkeypatch.setattr(macos, "_plist_path", lambda: tmp_path / "agent.plist")
        monkeypatch.setattr(macos, "_uid", lambda: 501)
        monkeypatch.setattr(macos, "_launchctl", lambda *args: recorded.append(args))
        return recorded

    def test_enable_writes_the_plist_and_bootstraps_it(self, calls, tmp_path):
        import plistlib

        from tokentray.autostart import macos

        macos.enable(COMMAND)
        payload = plistlib.loads((tmp_path / "agent.plist").read_bytes())
        assert payload["Label"] == macos.LABEL
        assert payload["ProgramArguments"] == COMMAND + ["--autostart"]
        assert payload["RunAtLoad"] is True
        # Restart on a crash, but honour a deliberate quit from the tray menu.
        assert payload["KeepAlive"] == {"SuccessfulExit": False}
        assert calls == [("bootstrap", "gui/501", str(tmp_path / "agent.plist"))]

    def test_registered_command_strips_the_autostart_flag(self, calls):
        from tokentray.autostart import macos

        macos.enable(COMMAND)
        assert macos.registered_command() == COMMAND

    def test_disable_boots_out_then_removes(self, calls, tmp_path):
        from tokentray.autostart import macos

        macos.enable(COMMAND)
        calls.clear()
        macos.disable()
        assert calls == [("bootout", f"gui/501/{macos.LABEL}")]
        assert macos.is_enabled() is False

    def test_disable_on_a_clean_machine_does_nothing(self, calls):
        from tokentray.autostart import macos

        macos.disable()
        assert calls == []

    def test_a_corrupt_plist_reads_as_unregistered(self, calls, tmp_path):
        from tokentray.autostart import macos

        (tmp_path / "agent.plist").write_text("not a plist", encoding="utf-8")
        assert macos.registered_command() is None


class FakeRegistryKey:
    def __init__(self, store: dict[str, str]) -> None:
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeWinreg:
    """Enough of winreg to drive the backend anywhere, including on POSIX."""

    HKEY_CURRENT_USER = object()
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def OpenKey(self, root, path, reserved=0, access=0):  # noqa: N802
        return FakeRegistryKey(self.values)

    CreateKeyEx = OpenKey  # noqa: N815

    def QueryValueEx(self, key, name):  # noqa: N802
        if name not in key.store:
            raise FileNotFoundError(name)
        return key.store[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):  # noqa: N802
        key.store[name] = value

    def DeleteValue(self, key, name):  # noqa: N802
        key.store.pop(name, None)


class TestWindowsAutostart:
    """HKCU Run key, driven through a stub so every runner exercises it."""

    @pytest.fixture
    def registry(self, monkeypatch):
        from tokentray.autostart import windows

        fake = FakeWinreg()
        monkeypatch.setattr(windows, "_winreg", lambda: fake)
        return fake

    def test_enable_stores_a_quoted_command_line(self, registry):
        from tokentray.autostart import windows

        assert windows.is_enabled() is False
        windows.enable([r"C:\Program Files\tokentray\tokentray-gui.exe"])
        assert windows.is_enabled() is True
        stored = registry.values[windows.VALUE_NAME]
        assert stored.endswith("--autostart")
        # A space in the path has to survive as one argument, not two.
        assert stored.startswith('"C:\\Program Files')

    def test_disable_clears_the_value(self, registry):
        from tokentray.autostart import windows

        windows.enable(COMMAND)
        windows.disable()
        assert windows.is_enabled() is False

    def test_disable_on_a_clean_machine_does_nothing(self, registry):
        from tokentray.autostart import windows

        windows.disable()
        assert windows.is_enabled() is False

    @pytest.mark.skipif(sys.platform != "win32", reason="needs CommandLineToArgvW")
    def test_a_windows_path_with_spaces_round_trips(self, registry):
        from tokentray.autostart import windows

        # shlex would mangle the backslashes; the backend uses the Win32 parser
        # that produced the string, so only Windows can prove this round trip.
        spaced = [r"C:\Program Files\tokentray\tokentray-gui.exe"]
        windows.enable(spaced)
        assert windows.registered_command() == spaced


class TestBackendDispatch:
    @pytest.mark.parametrize(
        "platform, module",
        [("win32", "windows"), ("darwin", "macos"), ("linux", "linux")],
    )
    def test_each_platform_gets_its_own_backend(self, platform, module, monkeypatch):
        monkeypatch.setattr(sys, "platform", platform)
        assert autostart._backend().__name__.endswith(module)

    def test_a_broken_backend_degrades_instead_of_raising(self, monkeypatch):
        def boom():
            raise RuntimeError("no session bus")

        monkeypatch.setattr(autostart, "_backend", boom)
        assert autostart.is_enabled() is False
        assert autostart.enable() is False
        assert autostart.disable() is False
        assert autostart.describe().startswith("unavailable")


class TestRuntimeDirectory:
    """Where the IPC socket lives, which is not the cache on Linux."""

    def test_linux_uses_the_xdg_runtime_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(paths, "user_runtime_dir", lambda *a, **k: str(tmp_path / "run"))
        assert paths.runtime_dir() == tmp_path / "run"

    @pytest.mark.parametrize("platform", ["darwin", "win32"])
    def test_elsewhere_it_is_the_state_directory(self, platform, monkeypatch, tmp_path):
        # platformdirs aliases the runtime dir to a cache path off Linux, and
        # cache cleaners delete sockets - a vanished socket reads as "not running".
        monkeypatch.setattr(sys, "platform", platform)
        monkeypatch.setattr(paths, "state_dir", lambda: tmp_path)
        assert paths.runtime_dir() == paths.state_dir()


class TestPrivateFiles:
    @pytest.mark.skipif(os.name == "nt", reason="POSIX modes do not exist on Windows")
    def test_private_writes_are_owner_only(self, tmp_path):
        target = tmp_path / "secrets.toml"
        paths.atomic_write_text(target, "token = 'x'", private=True)
        assert stat.S_IMODE(target.stat().st_mode) == 0o600

    def test_private_writes_succeed_on_every_platform(self, tmp_path):
        target = tmp_path / "secrets.toml"
        paths.atomic_write_text(target, "token = 'x'", private=True)
        assert target.read_text(encoding="utf-8") == "token = 'x'"


class TestWaylandPlugin:
    """Toast placement needs XWayland, so the plugin is chosen before Qt starts."""

    @pytest.fixture(autouse=True)
    def linux_session(self, monkeypatch):
        from tokentray import bootstrap as app_mod

        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        monkeypatch.setenv("DISPLAY", ":0")
        return app_mod

    def test_a_wayland_session_with_xwayland_is_redirected(self, linux_session):
        linux_session.select_platform_plugin(Config({}))
        assert os.environ["QT_QPA_PLATFORM"] == "xcb"

    def test_an_explicit_choice_is_left_alone(self, linux_session, monkeypatch):
        monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")
        linux_session.select_platform_plugin(Config({}))
        assert os.environ["QT_QPA_PLATFORM"] == "wayland"

    def test_the_escape_hatch_disables_the_redirect(self, linux_session):
        linux_session.select_platform_plugin(Config({"linux": {"force_xwayland": False}}))
        assert "QT_QPA_PLATFORM" not in os.environ

    def test_without_xwayland_there_is_nothing_to_redirect_to(self, linux_session, monkeypatch):
        monkeypatch.delenv("DISPLAY", raising=False)
        linux_session.select_platform_plugin(Config({}))
        assert "QT_QPA_PLATFORM" not in os.environ

    def test_other_platforms_are_untouched(self, linux_session, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        linux_session.select_platform_plugin(Config({}))
        assert "QT_QPA_PLATFORM" not in os.environ


class TestIpcRoundTrip:
    """One transport per platform: a named pipe on Windows, AF_UNIX elsewhere.

    Exercised for real rather than mocked, because the two halves are different
    code and only the running OS can say whether they agree.
    """

    @pytest.fixture
    def short_runtime(self, monkeypatch, isolated_config):
        """A socket path short enough for AF_UNIX.

        sun_path is capped near 104 bytes, and pytest's tmp_path is already past
        that before the filename is appended - so bind somewhere shallow.
        """
        import shutil
        import tempfile

        directory = pathlib.Path(tempfile.mkdtemp(prefix="tt", dir=tempfile.gettempdir()))
        monkeypatch.setattr(paths, "runtime_dir", lambda: directory)
        yield directory
        shutil.rmtree(directory, ignore_errors=True)

    def test_a_command_reaches_the_running_instance(self, qapp, short_runtime):
        received: list[str] = []

        def handler(command: str) -> dict:
            received.append(command)
            return {"ok": True, "pid": 4242, "echo": command}

        instance = ipc.SingleInstance(handler)
        assert instance.acquire() is True
        try:
            reply = self._send(qapp, ipc.CMD_STATUS)
            assert reply is not None, "no reply from the listening instance"
            assert reply["pid"] == 4242
            assert reply["echo"] == ipc.CMD_STATUS
            assert received == [ipc.CMD_STATUS]
        finally:
            instance.release()

    def test_a_second_instance_stands_down(self, qapp, short_runtime):
        import threading

        first = ipc.SingleInstance(lambda command: {"ok": True})
        assert first.acquire() is True
        try:
            second = ipc.SingleInstance(lambda command: {"ok": True})
            result: dict[str, bool] = {}
            thread = threading.Thread(
                target=lambda: result.setdefault("acquired", second.acquire()), daemon=True
            )
            thread.start()
            deadline = time.monotonic() + 10
            while thread.is_alive() and time.monotonic() < deadline:
                qapp.processEvents()
            thread.join(timeout=2)
            assert result.get("acquired") is False
        finally:
            first.release()

    def test_nothing_listening_reads_as_not_running(self, short_runtime):
        assert ipc.send_command(ipc.CMD_STATUS) is None
        assert ipc.is_running() is False

    @staticmethod
    def _send(qapp, command: str) -> dict | None:
        """Send from a worker thread while the Qt server pumps its event loop."""
        import threading

        box: dict[str, dict | None] = {}
        # On Windows, QLocalServer publishes the named pipe on the next Qt turn.
        # Give it that turn before the worker attempts an immediate open.
        qapp.processEvents()
        thread = threading.Thread(
            target=lambda: box.setdefault("reply", ipc.send_command(command)),
            daemon=True,
        )
        thread.start()
        deadline = time.monotonic() + 10
        while thread.is_alive() and time.monotonic() < deadline:
            qapp.processEvents()
        thread.join(timeout=2)
        return box.get("reply")


class TestSecondLaunch:
    """A launch that loses the single-instance race has to say why it ended."""

    @pytest.fixture
    def lose_race(self, qapp, isolated_config, monkeypatch):
        from tokentray import app as app_mod
        from tokentray.core import i18n

        def run(reply):
            controller = app_mod.Controller(qapp, Config({"poll_interval": 120}))
            monkeypatch.setattr(controller._instance, "acquire", lambda: False)
            monkeypatch.setattr(app_mod.ipc, "send_command", lambda *a, **k: reply)
            assert controller.start() is False
            i18n.set_language("en")
            return controller

        return run

    def test_names_the_running_pid(self, lose_race, capsys, monkeypatch):
        from tokentray import app as app_mod
        from tokentray.core import i18n

        controller = lose_race({"ok": True, "pid": 4321})
        assert controller.handoff_reply["pid"] == 4321
        monkeypatch.setattr(sys, "platform", "linux")
        app_mod.report_handoff(controller.handoff_reply)
        out = capsys.readouterr().out
        assert "already running (pid 4321)" in out
        assert i18n.t("launch.tray_hidden_windows") not in out

    def test_points_windows_users_at_the_hidden_icons(self, lose_race, capsys, monkeypatch):
        from tokentray import app as app_mod
        from tokentray.core import i18n

        controller = lose_race({"ok": True, "pid": 4321})
        monkeypatch.setattr(sys, "platform", "win32")
        app_mod.report_handoff(controller.handoff_reply)
        assert i18n.t("launch.tray_hidden_windows") in capsys.readouterr().out

    def test_an_unanswered_lock_is_not_reported_as_running(self, lose_race, capsys):
        from tokentray import app as app_mod

        controller = lose_race(None)
        assert controller.handoff_reply is None
        app_mod.report_handoff(None)
        out = capsys.readouterr().out
        assert "not responding" in out
        assert "already running" not in out

    def test_the_gui_entry_has_no_console_and_does_not_mind(self, monkeypatch):
        from tokentray import app as app_mod

        monkeypatch.setattr(sys, "stdout", None)
        app_mod.report_handoff({"ok": True, "pid": 4321})

    def test_every_message_survives_a_korean_console(self):
        from tokentray.core import i18n

        i18n.set_language("ko")
        for key in ("launch.already_running", "launch.tray_hidden_windows", "launch.not_responding"):
            i18n.t(key, pid=4321, path="C:/log").encode("cp949")
