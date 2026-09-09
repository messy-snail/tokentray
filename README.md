# tokentray

[![English](https://img.shields.io/badge/README-English-2563EB?style=flat-square)](https://github.com/messy-snail/tokentray/blob/main/README.md)
[![한국어](https://img.shields.io/badge/README-%ED%95%9C%EA%B5%AD%EC%96%B4-64748B?style=flat-square)](https://github.com/messy-snail/tokentray/blob/main/README.ko.md)

[![CI](https://img.shields.io/github/actions/workflow/status/messy-snail/tokentray/ci.yml?style=flat-square&logo=githubactions&logoColor=white&label=CI)](https://github.com/messy-snail/tokentray/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide6-41CD52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-6B7280?style=flat-square)
[![License](https://img.shields.io/badge/license-MIT-22C55E?style=flat-square)][LICENSE]

<!-- Restore these two inside the badge row at the 0.1.0 tag. Until a
     package and a release exist they render as "not found" and
     "no releases", which reads as a broken project.
[![PyPI](https://img.shields.io/pypi/v/tokentray?style=flat-square&logo=pypi&logoColor=white&label=PyPI&color=3775A9)](https://pypi.org/project/tokentray/)
[![Release](https://img.shields.io/github/v/release/messy-snail/tokentray?style=flat-square&logo=github&logoColor=white&label=release&color=8957E5)](https://github.com/messy-snail/tokentray/releases/latest)
-->

A system-tray monitor for **Claude Code** and **OpenAI Codex** quota, with
readable desktop alerts before you run out. Windows, macOS and Linux, one
codebase.

> **Attribution.** tokentray is a from-scratch reimplementation derived from
> [haomingkoo/claude-codex-monitor](https://github.com/haomingkoo/claude-codex-monitor)
> (MIT), which pioneered this as a SwiftBar plugin plus a PowerShell tray
> script. The quota endpoints, the pace/burnout formulas and the colour tiers
> follow that project so the numbers stay comparable, and its MIT notice is
> preserved in [LICENSE]. Rewritten in Python because the original's
> two scripts had drifted: Windows never got reset reminders, phone alerts, or
> alerts for Codex at all.

## What it shows

- **Claude Code** - 5-hour session, 7-day window, per-model Opus/Sonnet
  sub-limits once you use them, and pay-as-you-go Extra Usage.
- **Codex** - whichever rate-limit windows your plan actually reports (a
  weekly-only plan shows one `7d` row, not a mislabelled `5h` one), plus credits.
- For every window: remaining %, time to reset, **pace** (1.0x means you will
  land exactly at zero when it resets) and a burnout projection.

The tray icon is a ring that drains clockwise from the top, coloured green
above 50%, amber to 20%, red below. With both providers set up it becomes two
rings: Claude outside, Codex inside. Each drains a full turn, so both are read
the same way.

## Install

> **0.1.0 is not released yet.** Linux still has an unverified desktop, so
> there is no PyPI package and no packaged build to download. Install from
> source until it ships - everything below the install step works the same.

```bash
git clone https://github.com/messy-snail/tokentray
cd tokentray
uv tool install .
```

Once 0.1.0 is out, this becomes `uv tool install tokentray`, or a packaged
build for your platform from
[Releases](https://github.com/messy-snail/tokentray/releases) - no Python
needed.

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
| `tokentray webhook setup/test` | Configure and test Slack, Discord, ntfy, or a generic webhook |
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
| `webhook.enabled` / `.kind` | off | One of `slack`, `discord`, `ntfy`, or `generic` |
| `codex.refresh` | `false` | Let tokentray refresh the Codex token |
| `linux.force_xwayland` | `true` | See below |

Choose **Notification integrations…** from the tray menu to configure one
outbound destination, validate its URL and send a test. Slack and Discord use
their Incoming Webhook feature; the URL is stored in the OS keyring rather than
the regular config file. You can also configure it from a terminal:

```bash
tokentray webhook setup --service slack
tokentray webhook test
```

Slack takes the sender name and icon from the Slack app that owns the webhook,
so set the included `packaging/resources/tokentray-512.png` as that app's icon.
Discord likewise lets you set the webhook avatar in the channel settings.

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
Builds are arm64 only - there is no Intel build. The CLI ships inside the
bundle, so `status`, `doctor` and `autostart` are at
`/Applications/tokentray.app/Contents/MacOS/tokentray`; symlink it onto your
PATH if you want it as plain `tokentray`. Claude Code keeps its credentials in
the login keychain rather than a file on macOS, so the first read may raise a
keychain authorization prompt.

**Linux.** Shipped as a tarball only - no `.deb`, AppImage or Flatpak. Run
`./install.sh` from the unpacked archive to get a launcher entry and an icon
(per-user, no root; `./install.sh --uninstall` reverses it). GNOME needs the
AppIndicator extension for a tray at all; KDE works out of the box. Some
distributions need `libxcb-cursor0` installed. Under
Wayland, tokentray runs through XWayland by default because Wayland gives
clients no say in window placement, which would scatter toasts wherever the
compositor likes; set `linux.force_xwayland = false` for native Wayland and
notification-centre alerts instead. Without a SecretService daemon, pasted
tokens fall back to an owner-only file and setup tells you so.

## Privacy

Tokens go to their own vendor over HTTPS and nowhere else. The only three hosts
tokentray contacts are `api.anthropic.com`, `chatgpt.com` and `auth.openai.com`
(plus your webhook, if you configure one). There is no telemetry. On macOS and Linux
the caches and the fallback secret file are written owner-only (`0600`); on
Windows they inherit the ACL of your user profile directory, which is
user-scoped by default but not narrowed further.

## Development

```bash
uv sync
uv run pytest
```

Widget tests run under Qt's offscreen platform, so they prove the code works,
not that it looks right - [MANUAL_TEST.md] covers the rest.

Packaged builds:

```bash
uv run pyinstaller --noconfirm --distpath dist --workpath build packaging/tokentray.spec
./packaging/smoke.sh
```

`smoke.sh` is what CI and the release workflow both run against a fresh bundle -
it checks that both executables exist, that the windowed one answers `--version`
instead of starting an event loop, and that the macOS bundle launches the GUI
rather than the CLI.

The icon files are generated from the same painter that draws the tray mark, so
they never drift from it. Re-run and commit after changing the mark:

```bash
QT_QPA_PLATFORM=offscreen uv run python packaging/make_icons.py
```

On a Linux machine, `./scripts/verify-linux.sh` runs everything about a desktop
that can be checked without a person watching, and prints what is left for
[MANUAL_TEST.md].

## License

MIT - see [LICENSE]. tokentray bundles Qt via PySide6, which is LGPLv3;
packaged builds include it as a dynamically linked library.

<!-- Absolute, because this file is also the PyPI long description and a
     relative link there resolves against pypi.org. -->
[LICENSE]: https://github.com/messy-snail/tokentray/blob/main/LICENSE
[MANUAL_TEST.md]: https://github.com/messy-snail/tokentray/blob/main/MANUAL_TEST.md
