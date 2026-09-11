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

A system-tray monitor for **Claude Code** and **OpenAI Codex** usage limits.
Check your remaining quota and get desktop alerts before it runs out.
Available for Windows, macOS and Linux.

> **Attribution.** tokentray is a from-scratch reimplementation derived from
> [haomingkoo/claude-codex-monitor](https://github.com/haomingkoo/claude-codex-monitor)
> (MIT), originally a SwiftBar plugin and a PowerShell tray script. tokentray
> follows its quota endpoints, pace and exhaustion formulas, and colour tiers.
> Its MIT notice is preserved in [LICENSE]. The Python implementation brings
> a shared interface and notification features to all three platforms.

## What it shows

- **Claude Code** - 5-hour and 7-day limits, Opus/Sonnet limits once used,
  and pay-as-you-go Extra Usage.
- **Codex** - the usage periods reported for your plan, model-specific limits,
  and credits. A weekly-only account limit appears as a 7-day row. Model-specific
  limits are shown even at 0% usage, so any separate 5-hour limit remains visible.
- For each period: remaining percentage, time to reset, **usage pace**, and
  estimated time to exhaustion. A pace of 1.0x means the quota is projected to
  run out at reset if your average usage rate stays the same.

The tray icon uses rings that drain clockwise from the top. With both services
enabled, Claude is outside and Codex is inside. Colour follows the remaining
percentage rounded down to a whole number: green above 50%, amber from 21% to
50%, and red at 20% or below. A service with no usage data has a grey ring.

## Install

> **0.1.0 is not released yet.** Linux desktop validation is still pending.
> There is no PyPI package or packaged download yet; use the source installation
> below.

```bash
git clone https://github.com/messy-snail/tokentray
cd tokentray
uv tool install .
```

For 0.1.0, the planned installation options are `uv tool install tokentray`
and platform-specific downloads from
[Releases](https://github.com/messy-snail/tokentray/releases).
Packaged downloads will not require a separate Python installation.

Then:

```bash
tokentray setup
```

Setup first asks for a language, then shows CLI availability and credential status
separately. Install and sign in to [Claude Code](https://code.claude.com/docs/en/setup)
or [Codex](https://developers.openai.com/codex/cli/); you only need the service you use.
Existing credentials and manual tokens can work even if the CLI is not found.
A detected token is shown as unverified until a usage request succeeds.

For missing or expired credentials, choose login, installation instructions, or
check again. You can also skip, disable a provider, or paste a token. Setup offers
to start TokenTray when you log in to your computer.

## Commands

| Command | Description |
|---|---|
| `tokentray` | Start the tray app |
| `tokentray setup` | Interactive first-run configuration |
| `tokentray status` | Print current quota (asks the running app first) |
| `tokentray open` / `refresh` / `stop` | Control a running instance |
| `tokentray doctor` | Check credentials, keyring, tray and notification delivery |
| `tokentray config get/set/path` | Read and write settings |
| `tokentray state reset --welcome/--alerts/--all` | Re-arm the first-run notice or the alert memory |
| `tokentray webhook setup/test` | Configure and test Slack, Discord, ntfy, or a generic webhook |
| `tokentray autostart enable/disable/status` | Manage start-at-login |

## Login credentials

tokentray reads the credentials saved on your machine by Claude Code and Codex.
**Claude token refresh is left to Claude Code** to avoid conflicting updates.
When a login expires, click **Log in** in the detail panel or the in-app alert.
TokenTray opens a terminal running `claude auth login` or `codex login` on Windows,
macOS, or Linux. It watches for credential changes for up to five minutes and
refreshes usage after a change. Cancelling the wait does not close your terminal;
you can finish signing in and refresh later. If no terminal can be opened, copy
the displayed command. If the CLI is not found, open the installation guide and
check again; an installed CLI may also be missing from the app's `PATH`.

`tokentray doctor` shows the same local CLI and credential detection results.
Opening an installation guide does not install software automatically.

| Service | Location |
|---|---|
| Claude Code | `~/.claude/.credentials.json` (or `$CLAUDE_CONFIG_DIR`), falling back to the macOS login keychain |
| Codex | `~/.codex/auth.json` (or `$CODEX_HOME`) |

If the credentials file contains plan metadata but no usable `accessToken`,
`tokentray doctor` reports `no token in file`. This can happen when authentication
is handled elsewhere, such as through a desktop app, and does not necessarily
mean you are logged out.

You can also paste a token during `setup`. It is stored in your OS keyring,
with a separate local secret file as a fallback if the keyring is unavailable
(see Privacy). A pasted Claude token is temporary: tokentray cannot renew it
when it expires.

Codex token refresh is **opt-in** (`tokentray config set codex.refresh true`)
because file-based credentials share `auth.json` with the Codex CLI. Before
writing refreshed credentials, tokentray re-reads that file and skips the write
if the CLI has changed it in the meantime.

## Configuration

`tokentray config path` prints the configuration and data paths. `tokentray config
set` hands the change to a running instance, so thresholds, reminders, popup
position and duration, and `native_notifications` all apply straight away;
`poll_interval` and `language` still need a restart. Common settings:

| Key | Default | Description |
|---|---|---|
| `poll_interval` | `120` | Seconds between checks (minimum 30) |
| `thresholds` | `[50, 25, 10]` | Remaining % that trigger an alert |
| `remind_before` | `[60, 30, 10]` | Reminder times in minutes before reset; empty disables |
| `language` | from locale | `en` or `ko` |
| `popup.position` | `auto` | Which corner toasts stack from: `auto`, `bottom-right`, `top-right`. `auto` follows the platform - top on macOS, bottom elsewhere |
| `popup.duration` | `8` | Seconds a toast stays up |
| `native_notifications` | Windows: `false`; others: `true` | Opt into OS alerts on Windows; additional OS delivery elsewhere. Also applies to **Test notification** |
| `webhook.enabled` / `webhook.kind` | `false` / `ntfy` | Enable external alerts and choose `slack`, `discord`, `ntfy`, or `generic` |
| `codex.refresh` | `false` | Let tokentray refresh the Codex token |
| `linux.force_xwayland` | `true` | See below |

Choose **Notification integrations…** from the tray menu to configure one
outbound destination, validate its URL and send a test. Slack and Discord use
their Incoming Webhook feature. The URL is stored in the OS keyring, or a separate
local secret file if the keyring is unavailable (see Privacy). You can also
configure it from a terminal:

```bash
tokentray webhook setup --service slack
tokentray webhook test
```

> **Notification requirements**
>
> External alerts are sent by a device running tokentray with an internet
> connection. Monitoring usage also requires valid login credentials. Quitting
> the app, shutting down the device, or putting it to sleep stops its checks and
> delivery. Closing the detail window leaves monitoring active in the tray.
>
> Multiple devices monitoring the same account and sending to the same
> destination can produce duplicate alerts. Enable external alerts on only one
> device; the others can still show desktop alerts. There is no automatic
> handover if the sending device stops running.

Slack takes the sender name and icon from the Slack app that owns the webhook,
so set the included `packaging/resources/tokentray-512.png` as that app's icon.
Discord likewise lets you set the webhook avatar in the channel settings.

## Notifications

Windows uses custom quota cards by default, with provider icons and progress bars.
**Test notification** fetches fresh usage in the background and shows one card per
service, with a labelled remaining-quota meter and reset time for each limit.
The test menu is disabled while fetching; repeated requests share that test.
Unavailable services show their status, and cached results are marked as previous
data. The test updates the panel without firing automatic alerts, changing their
history, or sending webhooks. Set `native_notifications = true` to opt into
Windows OS banners instead (one text summary for the test). Unsupported native delivery or a submission error also
falls back to custom cards; a successful submission does not guarantee that
Windows displays a banner. Windows controls native banner position and duration;
`popup.position` and `popup.duration` apply only to custom cards.

Welcome notices and batches containing login recovery alerts retain custom cards
without an additional Windows banner, preserving their existing action buttons
and grouping. macOS and Linux retain custom cards with optional OS delivery.
External notifications follow their own settings independently.

On macOS, notification-centre delivery from a tray icon is unreliable: Qt's macOS
backend still uses the notification API Apple deprecated in macOS 11, and macOS
wants a signed bundle, while the builds here are ad-hoc signed only. The in-app
toast is therefore the primary channel, not a fallback. `tokentray doctor` reports
the situation for your build, **Test notification** in the tray menu fires both
channels so you can tell them apart, and every OS attempt is written to the log
(**Open log** in the tray menu, or `tokentray config path`) - so a channel that
drops notifications silently still leaves evidence.

## Platform notes

**Windows.** New tray icons may appear under hidden icons in the taskbar. The
welcome popup links to the relevant setting. Packaged builds are unsigned, so
SmartScreen may show a warning; choose *More info* then *Run anyway* to continue.
When installed with `uv tool`, the background process appears in Task Manager
as `pythonw.exe`.

**macOS.** Builds are ad-hoc signed but not notarised. If Gatekeeper blocks a
downloaded app, remove its quarantine attribute:

```bash
xattr -dr com.apple.quarantine /Applications/tokentray.app
```

The app is menu-bar only (`LSUIElement`), so there is no Dock icon by design.
Run `tokentray doctor` for the notification-centre verdict on your build. If you
use a menu bar manager (Bartender, Ice, Hidden Bar), note that it lists an
unbundled run as *Python* rather than *tokentray*.
Builds are arm64 only - there is no Intel build. The CLI ships inside the
bundle, so `status`, `doctor` and `autostart` are at
`/Applications/tokentray.app/Contents/MacOS/tokentray`; symlink it onto your
PATH to use `tokentray` directly. If Claude Code credentials are stored in the
login keychain, the first read may show a keychain access prompt.

**Linux.** Builds are x86_64 only. Shipped as a tarball only - no `.deb`,
AppImage or Flatpak. Run `./install.sh` from the unpacked archive to get a
launcher entry and an icon (per-user, no root; `./install.sh --uninstall`
reverses it). GNOME needs the AppIndicator extension for a tray at all; KDE
works out of the box. Some distributions need `libxcb-cursor0` installed. Under
Wayland, tokentray runs through XWayland by default because Wayland gives
clients limited control over popup placement. Set `linux.force_xwayland = false`
for native Wayland and notification-centre alerts. Without a working keyring
service such as SecretService, secrets fall back to a local file with owner-only
permissions, and setup reports the fallback.

## Privacy

Claude and Codex login tokens are sent only to their respective services over
HTTPS: `api.anthropic.com`, `chatgpt.com` and `auth.openai.com`. Configured
webhooks receive notification content, not those login tokens. There is no
telemetry. On macOS and Linux, the caches and the fallback secret file are
written owner-only (`0600`); on Windows they inherit the ACL of your user
profile directory, which is
user-scoped by default but not narrowed further.

## Development

```bash
uv sync
uv run pytest
```

Widget tests run under Qt's offscreen platform. Real desktop appearance and
external notification delivery require the checks in [MANUAL_TEST.md].

Packaged builds:

```bash
uv run pyinstaller --noconfirm --distpath dist --workpath build packaging/tokentray.spec
./packaging/smoke.sh
```

`smoke.sh` is what CI and the release workflow both run against a fresh bundle -
it checks that both executables exist, that the windowed one answers `--version`
instead of starting an event loop, and that the macOS bundle launches the GUI
rather than the CLI.

Icon files are generated by the tray icon renderer. Regenerate and commit them
after changing the icon design:

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
