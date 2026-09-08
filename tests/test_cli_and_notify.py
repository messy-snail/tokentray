from __future__ import annotations

import httpx
import pytest
import respx
from typer.testing import CliRunner

from tokentray import ipc
from tokentray.cli import app as cli_app
from tokentray.core.alerts import AlertEvent
from tokentray.core.config import Config
from tokentray.core.secrets import CLAUDE_ACCESS_TOKEN, WEBHOOK_URL, SecretStore
from tokentray.notify.configuration import save_destination
from tokentray.notify.formatting import summarize
from tokentray.notify.webhook import Webhook, validate_destination
from tokentray.providers.claude import USAGE_URL as CLAUDE_URL
from tokentray.providers.codex import USAGE_URL as CODEX_URL

runner = CliRunner()


def output(result) -> str:
    """stdout plus stderr; error paths write to stderr and Click keeps them apart."""
    try:
        return (result.stdout or "") + (result.stderr or "")
    except ValueError:  # older Click merges the streams
        return result.output or ""

CLAUDE_BODY = {
    "five_hour": {"utilization": 48.0, "resets_at": "2099-01-01T00:00:00Z"},
    "seven_day": {"utilization": 19.0, "resets_at": "2099-01-08T00:00:00Z"},
}


class TestStatusCommand:
    def test_renders_windows_from_a_live_fetch(self, isolated_config, claude_credentials):
        with respx.mock:
            respx.get(CLAUDE_URL).mock(return_value=httpx.Response(200, json=CLAUDE_BODY))
            respx.get(CODEX_URL).mock(return_value=httpx.Response(404))
            result = runner.invoke(cli_app, ["status", "--local"])
        assert result.exit_code == 0
        assert "5-Hour Session" in result.stdout
        assert "52% remaining" in result.stdout

    def test_exits_non_zero_when_nothing_is_configured(self, isolated_config):
        result = runner.invoke(cli_app, ["status", "--local"])
        assert result.exit_code == 1
        assert "Not logged into" in output(result)

    def test_prefers_a_running_instance_over_a_fresh_fetch(self, isolated_config, monkeypatch):
        payload = {
            "ok": True,
            "pid": 4242,
            "paused": False,
            "providers": [
                {
                    "title": "Claude Code (max)",
                    "status": "ok",
                    "message": "",
                    "source": "live",
                    "windows": [
                        {
                            "label": "5-Hour Session",
                            "remaining": 52,
                            "text": "52% remaining",
                            "tier": "green",
                            "refills": "Refills in 2h 0m",
                            "burns": "",
                            "pace": "Pace: 1.0x",
                        }
                    ],
                    "notes": [],
                }
            ],
        }
        monkeypatch.setattr("tokentray.ipc.send_command", lambda *a, **k: payload)
        # No respx mock: any HTTP call here would be a bug, not a test failure.
        result = runner.invoke(cli_app, ["status"])
        assert result.exit_code == 0
        assert "52% remaining" in result.stdout
        assert "pid 4242" in result.stdout

    def test_paused_state_is_surfaced(self, isolated_config, monkeypatch):
        monkeypatch.setattr(
            "tokentray.ipc.send_command",
            lambda *a, **k: {"ok": True, "pid": 1, "paused": True, "providers": []},
        )
        result = runner.invoke(cli_app, ["status"])
        assert "alerts paused" in result.stdout


class TestConfigCommand:
    def test_set_then_get_round_trips(self, isolated_config):
        assert runner.invoke(cli_app, ["config", "set", "poll_interval", "300"]).exit_code == 0
        result = runner.invoke(cli_app, ["config", "get", "poll_interval"])
        assert "300" in result.stdout

    def test_nested_key(self, isolated_config):
        assert runner.invoke(cli_app, ["config", "set", "codex.refresh", "true"]).exit_code == 0
        assert "True" in runner.invoke(cli_app, ["config", "get", "codex.refresh"]).stdout

    def test_unknown_key_is_rejected(self, isolated_config):
        # Typos must not silently create dead configuration entries.
        result = runner.invoke(cli_app, ["config", "set", "poll_intervals", "300"])
        assert result.exit_code == 1

    def test_get_without_a_key_lists_everything(self, isolated_config):
        result = runner.invoke(cli_app, ["config", "get"])
        assert "poll_interval" in result.stdout
        assert "webhook.enabled" in result.stdout


class TestOtherCommands:
    def test_version(self):
        assert runner.invoke(cli_app, ["--version"]).exit_code == 0

    def test_doctor_reports_credentials_and_paths(self, isolated_config):
        result = runner.invoke(cli_app, ["doctor"])
        assert result.exit_code == 0
        assert "claude credentials" in result.stdout
        assert "secret backend" in result.stdout

    def test_doctor_distinguishes_an_empty_token_file(self, isolated_config, claude_credentials):
        import json

        claude_credentials.write_text(
            json.dumps({"claudeAiOauth": {"accessToken": ""}}), encoding="utf-8"
        )
        assert "no token in file" in runner.invoke(cli_app, ["doctor"]).stdout

    @pytest.mark.parametrize("command", ["open", "refresh", "stop"])
    def test_commands_needing_the_app_fail_cleanly(self, isolated_config, monkeypatch, command):
        monkeypatch.setattr("tokentray.ipc.send_command", lambda *a, **k: None)
        result = runner.invoke(cli_app, [command])
        assert result.exit_code == 1
        assert "not running" in output(result)

    def test_autostart_status_does_not_change_anything(self, isolated_config):
        assert runner.invoke(cli_app, ["autostart", "status"]).exit_code == 0


class TestSetupWizard:
    def _answers(self, monkeypatch, prompts: list[str], confirms: list[bool]):
        prompt_iter, confirm_iter = iter(prompts), iter(confirms)
        monkeypatch.setattr("typer.prompt", lambda *a, **k: next(prompt_iter))
        monkeypatch.setattr("typer.confirm", lambda *a, **k: next(confirm_iter))

    def test_detected_providers_need_no_input(
        self, isolated_config, monkeypatch, claude_credentials, codex_credentials, tmp_path
    ):
        from tokentray.setup_wizard import run

        self._answers(monkeypatch, prompts=["en"], confirms=[False, False])
        config = Config({}, tmp_path / "config.toml")
        assert run(config, SecretStore(tmp_path / "s.toml"), launch=False) == 0
        assert config.get("claude.enabled") is True
        assert config.get("codex.enabled") is True

    def test_pasted_token_is_stored(self, isolated_config, monkeypatch, tmp_path):
        from tokentray.setup_wizard import run

        store = SecretStore(tmp_path / "s.toml")
        monkeypatch.setattr(store, "_keyring", lambda: None)
        # claude: paste + token, codex: skip, then language, then no autostart/launch.
        self._answers(
            monkeypatch,
            prompts=["p", "sk-pasted", "s", "ko"],
            confirms=[False, False],
        )
        config = Config({}, tmp_path / "config.toml")
        run(config, store, launch=False)
        assert store.get(CLAUDE_ACCESS_TOKEN) == "sk-pasted"
        assert config.get("language") == "ko"

    def test_disabling_a_provider_is_persisted(self, isolated_config, monkeypatch, tmp_path):
        from tokentray.setup_wizard import run

        self._answers(monkeypatch, prompts=["d", "s", "en"], confirms=[False, False])
        config = Config({}, tmp_path / "config.toml")
        run(config, SecretStore(tmp_path / "s.toml"), launch=False)
        assert config.get("claude.enabled") is False


class TestWebhook:
    def test_disabled_webhook_sends_nothing(self):
        with respx.mock:
            route = respx.post("https://ntfy.sh/topic")
            Webhook(enabled=False, kind="ntfy", url="https://ntfy.sh/topic").send(
                AlertEvent(kind="threshold", key="k", title="t", body="b")
            )
            assert not route.called

    def test_ntfy_carries_title_and_priority(self):
        import time

        with respx.mock:
            route = respx.post("https://ntfy.sh/topic").mock(return_value=httpx.Response(200))
            Webhook(enabled=True, kind="ntfy", url="https://ntfy.sh/topic").send(
                AlertEvent(kind="threshold", key="k", title="Warning", body="10% left",
                           priority="urgent")
            )
            for _ in range(50):  # delivery happens on a worker thread
                if route.called:
                    break
                time.sleep(0.02)
        assert route.called
        request = route.calls[0].request
        assert request.headers["Priority"] == "urgent"
        assert request.headers["Title"] == "Warning"

    def test_non_latin1_title_is_escaped_for_the_header(self):
        import time

        with respx.mock:
            route = respx.post("https://ntfy.sh/t").mock(return_value=httpx.Response(200))
            Webhook(enabled=True, kind="ntfy", url="https://ntfy.sh/t").send(
                AlertEvent(kind="threshold", key="k", title="사용량 경고", body="b")
            )
            for _ in range(50):
                if route.called:
                    break
                time.sleep(0.02)
        # HTTP headers cannot carry raw UTF-8; sending it raw raises inside httpx.
        assert route.called
        route.calls[0].request.headers["Title"].encode("latin-1")

    def test_broken_endpoint_does_not_raise(self):
        with respx.mock:
            respx.post("https://ntfy.sh/t").mock(side_effect=httpx.ConnectError("down"))
            Webhook(enabled=True, kind="ntfy", url="https://ntfy.sh/t").send(
                AlertEvent(kind="threshold", key="k", title="t", body="b")
            )

    def test_from_config(self):
        webhook = Webhook.from_config(
            Config({"webhook": {"enabled": True, "kind": "generic", "url": "https://x/y"}})
        )
        assert webhook.enabled and webhook.kind == "generic"

    def test_slack_uses_blocks_and_fallback_text(self):
        import json

        url = "https://hooks.slack.com/services/T/B/secret"
        with respx.mock:
            route = respx.post(url).mock(return_value=httpx.Response(200, text="ok"))
            result = Webhook(enabled=True, kind="slack", url=url).deliver(
                AlertEvent(
                    kind="threshold", key="codex.7d", title="tokentray · Codex",
                    body="7d: 10% remaining", provider="codex", priority="urgent",
                )
            )
        assert result.ok
        payload = json.loads(route.calls[0].request.content)
        assert payload["blocks"][0]["text"]["text"] == "tokentray · Codex"
        assert "10%" in payload["text"]

    def test_discord_uses_embed_and_disables_mentions(self):
        import json

        url = "https://discord.com/api/webhooks/123/secret"
        with respx.mock:
            route = respx.post(url).mock(return_value=httpx.Response(200, json={}))
            result = Webhook(enabled=True, kind="discord", url=url).deliver(
                AlertEvent(
                    kind="threshold", key="claude.5h", title="tokentray · Claude Code",
                    body="5-Hour Session: 25% remaining", provider="claude", tier="orange",
                )
            )
        assert result.ok
        request = route.calls[0].request
        payload = json.loads(request.content)
        assert request.url.params["wait"] == "true"
        assert payload["allowed_mentions"] == {"parse": []}
        assert payload["embeds"][0]["footer"]["text"] == "Claude Code"

    def test_service_urls_are_validated(self):
        assert validate_destination("slack", "https://example.com/hook")
        assert validate_destination("discord", "http://discord.com/api/webhooks/1/x")
        assert not validate_destination("discord", "https://discord.com/api/webhooks/1/x")
        assert not validate_destination("generic", "http://localhost:8080/hook")

    def test_rate_limit_waits_once_then_retries(self, monkeypatch):
        url = "https://discord.com/api/webhooks/123/secret"
        waits: list[float] = []
        monkeypatch.setattr("tokentray.notify.webhook.time.sleep", waits.append)
        with respx.mock:
            route = respx.post(url).mock(
                side_effect=[
                    httpx.Response(429, json={"retry_after": 0.25}),
                    httpx.Response(200, json={}),
                ]
            )
            result = Webhook(enabled=True, kind="discord", url=url).deliver(
                AlertEvent(kind="info", key="test", title="tokentray", body="test")
            )
        assert result.ok
        assert route.call_count == 2
        assert waits == [0.25]

    def test_settings_move_url_into_secret_store(self, tmp_path, monkeypatch):
        store = SecretStore(tmp_path / "secrets.toml")
        monkeypatch.setattr(store, "_keyring", lambda: None)
        config = Config({}, tmp_path / "config.toml")
        settings = save_destination(
            config,
            enabled=True,
            kind="slack",
            url="https://hooks.slack.com/services/T/B/secret",
            store=store,
        )
        assert settings.enabled and settings.configured
        assert store.get(WEBHOOK_URL).endswith("/secret")
        assert Config.load(tmp_path / "config.toml").get("webhook.url") == ""

    def test_config_output_does_not_reveal_legacy_url(self, isolated_config):
        config = Config.load()
        config.set("webhook.url", "https://hooks.slack.com/services/T/B/secret")
        config.save()
        result = runner.invoke(cli_app, ["config", "get", "webhook.url"])
        assert "secret" not in result.stdout
        assert "********" in result.stdout

    def test_mixed_summary_names_both_providers(self):
        summary = summarize(
            [
                AlertEvent(kind="threshold", key="claude.5h", title="c", body="b", provider="claude"),
                AlertEvent(kind="threshold", key="codex.7d", title="x", body="b", provider="codex"),
            ]
        )
        assert summary.title == "tokentray · Claude Code + Codex"
        assert "Claude Code 1" in summary.body
        assert "Codex 1" in summary.body


class TestIpcClient:
    def test_no_server_means_none(self, isolated_config):
        assert ipc.send_command(ipc.CMD_STATUS) is None
        assert ipc.is_running() is False

    def test_socket_name_is_per_user(self, isolated_config):
        assert ipc.socket_name()


class TestConsoleEncoding:
    """A Korean or Japanese Windows console is cp949/cp932, not UTF-8.

    Writing a tier emoji there raises UnicodeEncodeError and kills the command,
    which is how `tokentray status` first failed on this machine.
    """

    def test_emoji_is_replaced_when_unencodable(self, monkeypatch):
        from tokentray import cli

        monkeypatch.setattr(cli.sys, "stdout", _FakeStream("cp949"))
        assert cli._console_safe("🟢 ok") == "[ok] ok"

    def test_korean_survives_cp949(self, monkeypatch):
        from tokentray import cli

        monkeypatch.setattr(cli.sys, "stdout", _FakeStream("cp949"))
        assert cli._console_safe("7일 윈도우: 25% 남음") == "7일 윈도우: 25% 남음"

    def test_utf8_console_keeps_the_emoji(self, monkeypatch):
        from tokentray import cli

        monkeypatch.setattr(cli.sys, "stdout", _FakeStream("utf-8"))
        assert cli._console_safe("🟢") == "🟢"

    def test_pace_and_bar_glyphs_have_fallbacks(self, monkeypatch):
        from tokentray import cli

        monkeypatch.setattr(cli.sys, "stdout", _FakeStream("ascii"))
        rendered = cli._console_safe("■□ 🔥 ⚡")
        assert "?" not in rendered

    def test_status_does_not_crash_on_a_legacy_console(
        self, isolated_config, claude_credentials, monkeypatch
    ):
        from tokentray import cli

        monkeypatch.setattr(cli.sys, "stdout", _FakeStream("cp949"))
        with respx.mock:
            respx.get(CLAUDE_URL).mock(return_value=httpx.Response(200, json=CLAUDE_BODY))
            respx.get(CODEX_URL).mock(return_value=httpx.Response(404))
            result = runner.invoke(cli_app, ["status", "--local"])
        assert result.exit_code == 0


class _FakeStream:
    def __init__(self, encoding: str) -> None:
        self.encoding = encoding
