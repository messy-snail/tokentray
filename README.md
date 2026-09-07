# tokentray

[![CI](https://img.shields.io/github/actions/workflow/status/messy-snail/tokentray/ci.yml?style=flat-square&logo=githubactions&logoColor=white&label=CI)](https://github.com/messy-snail/tokentray/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tokentray?style=flat-square&logo=pypi&logoColor=white&label=PyPI&color=3775A9)](https://pypi.org/project/tokentray/)
[![Release](https://img.shields.io/github/v/release/messy-snail/tokentray?style=flat-square&logo=github&logoColor=white&label=release&color=8957E5)](https://github.com/messy-snail/tokentray/releases/latest)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide6-41CD52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-6B7280?style=flat-square)
[![License](https://img.shields.io/badge/license-MIT-22C55E?style=flat-square)](LICENSE)

**English** · [한국어](README.ko.md)

A system-tray monitor for **Claude Code** and **OpenAI Codex** quota, with
readable desktop alerts before you run out. Windows, macOS and Linux, one
codebase.

> **Attribution.** tokentray is a from-scratch reimplementation derived from
> [haomingkoo/claude-codex-monitor](https://github.com/haomingkoo/claude-codex-monitor)
> (MIT), which pioneered this as a SwiftBar plugin plus a PowerShell tray
> script. The quota endpoints, the pace/burnout formulas and the colour tiers
> follow that project so the numbers stay comparable, and its MIT notice is
> preserved in [LICENSE](LICENSE). Rewritten in Python because the original's
> two scripts had drifted: Windows never got reset reminders, phone alerts, or
> alerts for Codex at all.

## What it shows

- **Claude Code** - 5-hour session, 7-day window, per-model Opus/Sonnet
  sub-limits once you use them, and pay-as-you-go Extra Usage.
- **Codex** - whichever rate-limit windows your plan actually reports (a
  weekly-only plan shows one `7d` row, not a mislabelled `5h` one), plus credits.
- For every window: remaining %, time to reset, **pace** (1.0x means you will
  land exactly at zero when it resets) and a burnout projection.

The tray icon is a ring that drains from the top, coloured green above 50%,
amber to 20%, red below. With both providers set up it splits: Claude left,
Codex right.

## Install

```bash
uv tool install tokentray
```

Or download a packaged build for your platform from
[Releases](https://github.com/messy-snail/tokentray/releases) - no Python needed.

Then:

```bash
tokentray setup
```

Setup detects the logins you already have, picks a language from your desktop
locale, and offers to start tokentray at login.

## Commands

| Command | |
|---|---|
| `tokentray` | Start the tray app |
| `tokentray setup` | Interactive first-run configuration |
| `tokentray status` | Print current quota (asks the running app first) |
| `tokentray open` / `refresh` / `stop` | Control a running instance |
| `tokentray doctor` | Check credentials, keyring and tray availability |
| `tokentray config get/set/path` | Read and write settings |
| `tokentray autostart enable/disable/status` | Manage start-at-login |

## How it finds your tokens

tokentray reads the credentials the CLIs already keep on your machine and
**never refreshes Claude's token**: Claude Code owns it, and a second writer is
how people end up logged out. When it expires, tokentray says so and points you
at `claude`.

| | Location |
|---|---|
| Claude Code | `~/.claude/.credentials.json` (or `$CLAUDE_CONFIG_DIR`), falling back to the macOS login keychain |
| Codex | `~/.codex/auth.json` (or `$CODEX_HOME`) |

If a file holds no usable token - Claude Code writes plan metadata with a blank
`accessToken` when the session is authenticated elsewhere, such as through the
desktop app - `tokentray doctor` reports `no token in file` rather than claiming
you are logged out.

You can paste a token instead during `setup`, stored in your OS keyring. Worth
knowing before you do: a Claude token expires within hours and only Claude Code
can renew it, so pasting one is a stopgap, not a setup.

Codex token refresh is **opt-in** (`tokentray config set codex.refresh true`)
because it rewrites `auth.json`, a file the Codex CLI also owns. When enabled,
tokentray re-reads the file immediately before writing and backs off if the CLI
changed it in the meantime.

## Configuration

`tokentray config path` prints every location. Useful keys:

| Key | Default | |
|---|---|---|
| `poll_interval` | `120` | Seconds between checks (floor 30) |
| `thresholds` | `[50, 25, 10]` | Remaining % that trigger an alert |
| `remind_before` | `[60, 30, 10]` | Minutes before a reset to nudge; empty disables |
| `language` | from locale | `en` or `ko` |
| `popup.duration` | `8` | Seconds a toast stays up |
| `native_notifications` | `true` | Also send to the OS notification centre |
| `webhook.enabled` / `.kind` / `.url` | off | `ntfy` or `generic` JSON POST |
| `codex.refresh` | `false` | Let tokentray refresh the Codex token |
| `linux.force_xwayland` | `true` | See below |

## Why the notifications are drawn, not native

Native notifications are a secondary channel here, never the primary one. macOS
delivers them only from a signed bundle; Windows needs a registered
AppUserModelID and silently swallows the legacy balloon path under Focus Assist;
and the three platforms disagree about styling. A window tokentray draws itself
looks the same everywhere, always appears, and can show a meter - which is most
of the message.

## Platform notes

**Windows.** A new tray icon hides in the overflow flyout; the welcome popup
offers a button straight to that setting. Downloads are unsigned, so SmartScreen
will warn once - choose *More info* then *Run anyway*. When installed with
`uv tool`, the background process appears in Task Manager as `pythonw.exe`.

**macOS.** Builds are ad-hoc signed but not notarised, so Gatekeeper quarantines
them:

```bash
xattr -dr com.apple.quarantine /Applications/tokentray.app
```

The app is menu-bar only (`LSUIElement`), so there is no Dock icon by design.
Builds are arm64.

**Linux.** GNOME needs the AppIndicator extension for a tray at all; KDE works
out of the box. Some distributions need `libxcb-cursor0` installed. Under
Wayland, tokentray runs through XWayland by default because Wayland gives
clients no say in window placement, which would scatter toasts wherever the
compositor likes; set `linux.force_xwayland = false` for native Wayland and
notification-centre alerts instead. Without a SecretService daemon, pasted
tokens fall back to an owner-only file and setup tells you so.

## Privacy

Tokens go to their own vendor over HTTPS and nowhere else. The only three hosts
tokentray contacts are `api.anthropic.com`, `chatgpt.com` and `auth.openai.com`
(plus your webhook, if you configure one). There is no telemetry. Caches and the
fallback secret file are written owner-only.

## Development

```bash
uv sync
uv run pytest
```

Widget tests run under Qt's offscreen platform, so they prove the code works,
not that it looks right - [MANUAL_TEST.md](MANUAL_TEST.md) covers the rest.

Packaged builds:

```bash
uv run pyinstaller --noconfirm --distpath dist --workpath build packaging/tokentray.spec
```

## License

MIT - see [LICENSE](LICENSE). tokentray bundles Qt via PySide6, which is LGPLv3;
packaged builds include it as a dynamically linked library.
