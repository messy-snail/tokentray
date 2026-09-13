"""Tests for making a silent notification channel legible.

The bug these guard against is not "notifications fail" but "notifications fail
without leaving a trace": Qt's macOS backend accepts the call, returns normally
and delivers nothing. Every assertion below is about evidence surviving.
"""

from __future__ import annotations

import logging
import sys

import pytest

pytest.importorskip("PySide6")

from typer.testing import CliRunner  # noqa: E402

from tokentray import diagnostics  # noqa: E402
from tokentray.cli import app as cli_app  # noqa: E402
from tokentray.core.config import Config  # noqa: E402
from tokentray.ui import tray as tray_mod  # noqa: E402

runner = CliRunner()

ADHOC = "Identifier=io.github.messy-snail.tokentray\nSignature=adhoc\nTeamIdentifier=not set\n"
SIGNED = "Identifier=io.github.messy-snail.tokentray\nSignature=?\nTeamIdentifier=AB12CD34\n"
UNSIGNED = "/Applications/x.app: code object is not signed at all\n"


class TestTheAttemptIsRecorded:
    """Silence is the failure mode, so the log has to show the try, not the result."""

    @pytest.fixture
    def tray(self, qapp):
        return tray_mod.Tray()

    def test_an_attempt_is_always_logged(self, tray, caplog, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        # Support is pinned rather than read off the runner: the offscreen plugin
        # answers False on macOS and True on Linux, and this test is about the
        # attempt being recorded, not about what any one desktop reports.
        monkeypatch.setattr(tray_mod, "supports_messages", lambda: False)
        with caplog.at_level(logging.INFO, logger="tokentray.tray"):
            tray.show_message("tokentray", "body")
        record = caplog.records[-1]
        assert "native notification attempted" in record.getMessage()
        # One line carries both the fact that we tried and the reason it may have
        # gone nowhere.
        assert "supported=False" in record.getMessage()

    def test_a_raising_backend_is_logged_not_swallowed(self, tray, caplog, monkeypatch):
        def boom(*args):
            raise RuntimeError("no notification host")

        monkeypatch.setattr(tray._icon, "showMessage", boom)
        monkeypatch.setattr(tray_mod, "supports_messages", lambda: True)
        with caplog.at_level(logging.INFO, logger="tokentray.tray"):
            assert tray.show_message("tokentray", "body") is False
        record = caplog.records[-1]
        assert record.levelno == logging.WARNING
        assert "native notification failed" in record.getMessage()
        assert record.exc_info is not None

    def test_supports_messages_is_a_seam(self, tray, caplog, monkeypatch):
        monkeypatch.setattr(tray_mod, "supports_messages", lambda: True)
        with caplog.at_level(logging.INFO, logger="tokentray.tray"):
            tray.show_message("tokentray", "body")
        assert "supported=True" in caplog.records[-1].getMessage()


class TestWelcomeUsesTheSameGate:
    def test_welcome_native_goes_through_the_gate(self, qapp, isolated_config, monkeypatch):
        from tokentray import app as app_mod
        from tokentray.ui import popup

        controller = app_mod.Controller(qapp, Config({"poll_interval": 120}))
        monkeypatch.setattr(popup, "Toast", lambda **kw: kw)
        monkeypatch.setattr(controller.toasts, "show", lambda toast: None)
        sent = []
        monkeypatch.setattr(controller.tray, "show_message", lambda *a: sent.append(a))
        controller.dispatcher.set_native_enabled(False)
        controller._show_welcome()
        assert sent == []


class TestConfigReloadTakesEffect:
    """Settings held by objects other than Config used to need a restart."""

    def test_a_reload_hands_the_new_value_to_the_dispatcher(
        self, qapp, isolated_config, monkeypatch
    ):
        from tokentray import app as app_mod
        from tokentray import ipc
        from tokentray.core import paths

        controller = app_mod.Controller(qapp, Config({"poll_interval": 120}))
        recorded: list[bool] = []
        monkeypatch.setattr(controller.dispatcher, "set_native_enabled", recorded.append)

        paths.config_file().write_text(
            'language = "en"\nnative_notifications = false\n', encoding="utf-8"
        )
        controller._handle_command(ipc.CMD_RELOAD_CONFIG)
        assert recorded == [False]

    def test_a_reload_hands_over_the_toast_presentation(
        self, qapp, isolated_config, monkeypatch
    ):
        from tokentray import app as app_mod
        from tokentray import ipc
        from tokentray.core import paths

        controller = app_mod.Controller(qapp, Config({"poll_interval": 120}))
        paths.config_file().write_text(
            'language = "en"\n[popup]\nposition = "top-right"\nduration = 30\n',
            encoding="utf-8",
        )
        controller._handle_command(ipc.CMD_RELOAD_CONFIG)
        # Held by the ToastManager, not read per poll, so it has to be handed over.
        assert controller.toasts.position == "top-right"
        assert controller.toasts.duration == 30

    def test_setting_any_key_tells_the_running_app(self, isolated_config, monkeypatch):
        from tokentray import ipc

        sent: list[str] = []
        monkeypatch.setattr(ipc, "send_command", lambda c, timeout=2.0: sent.append(c))
        result = runner.invoke(cli_app, ["config", "set", "native_notifications", "false"])
        assert result.exit_code == 0
        assert sent == [ipc.CMD_RELOAD_CONFIG]


class TestBundleDetection:
    """Asked at startup, so it may not cost a subprocess."""

    def _bundle(self, tmp_path, *, plist: bool = True, in_macos_dir: bool = True):
        bundle = tmp_path / "tokentray.app"
        inner = bundle / "Contents" / ("MacOS" if in_macos_dir else "Resources")
        inner.mkdir(parents=True)
        exe = inner / "tokentray-gui"
        exe.write_text("", encoding="utf-8")
        if plist:
            (bundle / "Contents" / "Info.plist").write_text("", encoding="utf-8")
        return bundle, exe

    @pytest.fixture(autouse=True)
    def darwin(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")

    def test_a_bundle_is_recognised_without_a_subprocess(self, tmp_path, monkeypatch):
        bundle, exe = self._bundle(tmp_path)
        monkeypatch.setattr(sys, "executable", str(exe))
        monkeypatch.setattr(
            diagnostics, "_codesign", lambda b: pytest.fail("startup must not spawn")
        )
        assert diagnostics.macos_bundle() == bundle

    def test_a_bundle_without_an_info_plist_is_not_one(self, tmp_path, monkeypatch):
        _, exe = self._bundle(tmp_path, plist=False)
        monkeypatch.setattr(sys, "executable", str(exe))
        assert diagnostics.macos_bundle() is None

    def test_a_checkout_under_somebody_elses_app_is_not_one(self, tmp_path, monkeypatch):
        _, exe = self._bundle(tmp_path, in_macos_dir=False)
        monkeypatch.setattr(sys, "executable", str(exe))
        assert diagnostics.macos_bundle() is None

    def test_other_platforms_have_no_bundle(self, tmp_path, monkeypatch):
        _, exe = self._bundle(tmp_path)
        monkeypatch.setattr(sys, "executable", str(exe))
        monkeypatch.setattr(sys, "platform", "linux")
        assert diagnostics.macos_bundle() is None

    @pytest.mark.parametrize(
        "output, expected",
        [(ADHOC, "ad-hoc"), (SIGNED, "signed (AB12CD34)"), (UNSIGNED, "unsigned")],
    )
    def test_signature_states(self, tmp_path, monkeypatch, output, expected):
        bundle, _ = self._bundle(tmp_path)
        (bundle / "Contents" / "_CodeSignature").mkdir()
        (bundle / "Contents" / "_CodeSignature" / "CodeResources").write_text("", encoding="utf-8")
        monkeypatch.setattr(diagnostics, "_codesign", lambda b: output)
        assert diagnostics.bundle_signature(bundle) == expected

    def test_an_unreadable_signature_is_unknown(self, tmp_path, monkeypatch):
        bundle, _ = self._bundle(tmp_path)
        (bundle / "Contents" / "_CodeSignature").mkdir()
        (bundle / "Contents" / "_CodeSignature" / "CodeResources").write_text("", encoding="utf-8")

        def boom(bundle):
            raise TimeoutError

        monkeypatch.setattr(diagnostics, "_codesign", boom)
        assert diagnostics.bundle_signature(bundle) == "unknown"

    def test_a_missing_seal_costs_no_subprocess(self, tmp_path, monkeypatch):
        bundle, _ = self._bundle(tmp_path)
        monkeypatch.setattr(diagnostics, "_codesign", lambda b: pytest.fail("no seal to read"))
        assert diagnostics.bundle_signature(bundle) == "unsigned"


class TestDoctorReportsDelivery:
    def test_doctor_reports_the_macos_situation(self, isolated_config, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(diagnostics, "macos_bundle", lambda: None)
        result = runner.invoke(cli_app, ["doctor"])
        assert result.exit_code == 0
        assert "native alerts" in result.stdout
        assert "app bundle" in result.stdout
        assert diagnostics.MACOS_CONSEQUENCE in result.stdout

    def test_doctor_names_the_bundle_and_its_signature(self, isolated_config, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "darwin")
        bundle = tmp_path / "tokentray.app"
        monkeypatch.setattr(diagnostics, "macos_bundle", lambda: bundle)
        monkeypatch.setattr(diagnostics, "bundle_signature", lambda b: "ad-hoc")
        out = runner.invoke(cli_app, ["doctor"]).stdout
        assert f"app bundle          {bundle} (ad-hoc)" in out

    def test_doctor_stays_quiet_about_bundles_elsewhere(self, isolated_config, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        out = runner.invoke(cli_app, ["doctor"]).stdout
        assert "native alerts" in out
        assert "app bundle" not in out

    def test_the_setting_shows_up_in_the_report(self, isolated_config):
        from tokentray.core import paths

        paths.config_file().write_text(
            'language = "en"\nnative_notifications = false\n', encoding="utf-8"
        )
        assert "native alerts       off" in runner.invoke(cli_app, ["doctor"]).stdout


class TestDoctorFindsTheApp:
    def test_reports_a_running_instance(self, isolated_config, monkeypatch):
        from tokentray import ipc

        monkeypatch.setattr(ipc, "send_command", lambda *a, **k: {"ok": True, "pid": 4321})
        assert "running             yes (pid 4321)" in runner.invoke(cli_app, ["doctor"]).stdout

    def test_reports_nothing_running(self, isolated_config):
        assert "running             no" in runner.invoke(cli_app, ["doctor"]).stdout

    @pytest.mark.parametrize("platform, shown", [("win32", True), ("linux", False), ("darwin", False)])
    def test_the_hidden_icon_hint_is_for_windows(self, isolated_config, monkeypatch, platform, shown):
        from tokentray import connections
        from tokentray.core import i18n

        monkeypatch.setattr(sys, "platform", platform)
        monkeypatch.setattr(diagnostics, "macos_bundle", lambda: None)
        # shutil.which reads sys.platform too, and its win32 branch calls into
        # _winapi, which is None everywhere else. Stub the lookup, not the OS.
        monkeypatch.setattr(connections.shutil, "which", lambda *a, **k: None)
        out = runner.invoke(cli_app, ["doctor"]).stdout
        assert (i18n.t("launch.tray_hidden_windows") in out) is shown
