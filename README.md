<div align="center">

<img src="https://raw.githubusercontent.com/messy-snail/tokentray/main/packaging/resources/tokentray-256.png" alt="tokentray icon" width="96">

# tokentray

**Claude Code and Codex usage limits, right in your system tray.**

[![PyPI](https://img.shields.io/pypi/v/tokentray?style=flat-square&logo=pypi&logoColor=white&label=PyPI&color=3775A9)](https://pypi.org/project/tokentray/)
[![Release](https://img.shields.io/github/v/release/messy-snail/tokentray?style=flat-square&logo=github&logoColor=white&label=release&color=8957E5)](https://github.com/messy-snail/tokentray/releases/latest)
[![CI](https://img.shields.io/github/actions/workflow/status/messy-snail/tokentray/ci.yml?style=flat-square&logo=githubactions&logoColor=white&label=CI)](https://github.com/messy-snail/tokentray/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-22C55E?style=flat-square)][LICENSE]

![Windows](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0wIDBoMTEuNHYxMS40SDB6TTEyLjYgMEgyNHYxMS40SDEyLjZ6TTAgMTIuNmgxMS40VjI0SDB6TTEyLjYgMTIuNkgyNFYyNEgxMi42eiIvPjwvc3ZnPg%3D%3D)
![macOS](https://img.shields.io/badge/macOS-000000?style=for-the-badge&logo=apple&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)

**English** · [한국어](https://github.com/messy-snail/tokentray/blob/main/README.ko.md)

</div>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/messy-snail/tokentray/main/docs/images/hero-en-dark.png">
    <img src="https://raw.githubusercontent.com/messy-snail/tokentray/main/docs/images/hero-en-light.png" alt="tokentray detail panel, an alert card and tray icon states" width="760">
  </picture>
</p>

## Features

- 🟢 **Tray rings at a glance** - Claude on the outside, Codex inside. Green above
  50% left, amber down to 21%, red at 20% or below, grey without data.
- 📊 **Detail panel** - remaining %, time to reset, burn-out estimate and pace for
  every limit, including Opus/Sonnet and Codex model limits.
- 🔔 **Alerts before you run out** - at 50, 25 and 10% remaining, plus reminders
  before a reset.
- 🔑 **One-click login recovery** - opens a terminal with `claude auth login` or
  `codex login` when a login expires.
- 🌐 **Webhooks** - forward alerts to Slack, Discord, ntfy or any HTTP endpoint.
- 🖥️ **Windows, macOS and Linux**, in English or Korean.

A pace of **1.0x** means you will hit the limit exactly at reset if you keep
going at your average rate so far.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/messy-snail/tokentray/main/docs/images/login-recovery-en-dark.png">
    <img src="https://raw.githubusercontent.com/messy-snail/tokentray/main/docs/images/login-recovery-en-light.png" alt="Expired Claude Code login with Log in and Check again buttons" width="250">
  </picture>
  &nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/messy-snail/tokentray/main/docs/images/integrations-en-dark.png">
    <img src="https://raw.githubusercontent.com/messy-snail/tokentray/main/docs/images/integrations-en-light.png" alt="Notification integrations window with a Discord webhook" width="344">
  </picture>
</p>

## Install

> [!TIP]
> **uv is the recommended way.** It downloads a matching Python for you and keeps
> tokentray in its own environment, so nothing else on your system changes.

### ![uv](https://img.shields.io/badge/uv-recommended-DE5FE9?style=flat-square&logo=uv&logoColor=white)

Install uv once:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

`brew install uv` and `winget install --id=astral-sh.uv -e` work too. Then:

```bash
uv tool install tokentray
```

If the shell cannot find `tokentray` afterwards, run `uv tool update-shell` and
open a new terminal.

### pipx

```bash
pipx install tokentray
```

### pip

Needs Python 3.11-3.13. Install into a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install tokentray
```

### Standalone builds (no Python needed)

| Platform | Download | Then |
|---|---|---|
| ![Windows](https://img.shields.io/badge/Windows-0078D6?style=flat-square&logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0wIDBoMTEuNHYxMS40SDB6TTEyLjYgMEgyNHYxMS40SDEyLjZ6TTAgMTIuNmgxMS40VjI0SDB6TTEyLjYgMTIuNkgyNFYyNEgxMi42eiIvPjwvc3ZnPg%3D%3D) | [`tokentray-windows-x86_64.zip`](https://github.com/messy-snail/tokentray/releases/latest/download/tokentray-windows-x86_64.zip) | Unzip, run `tokentray\tokentray-gui.exe` |
| ![macOS](https://img.shields.io/badge/macOS-000000?style=flat-square&logo=apple&logoColor=white) | [`tokentray-macos-arm64.zip`](https://github.com/messy-snail/tokentray/releases/latest/download/tokentray-macos-arm64.zip) | Move `tokentray.app` to Applications |
| ![Linux](https://img.shields.io/badge/Linux-FCC624?style=flat-square&logo=linux&logoColor=black) | [`tokentray-linux-x86_64.tar.gz`](https://github.com/messy-snail/tokentray/releases/latest/download/tokentray-linux-x86_64.tar.gz) | Unpack, run `./install.sh` |

> [!IMPORTANT]
> Standalone builds are not code-signed, so Windows SmartScreen and macOS
> Gatekeeper warn on first launch. See
> [Platform notes](https://github.com/messy-snail/tokentray#platform-notes).

## Quick start

Sign in to [Claude Code](https://code.claude.com/docs/en/setup) or
[Codex](https://developers.openai.com/codex/cli/) first - one of them is enough.

```bash
tokentray setup              # choose a language, check logins, offer start-at-login
tokentray                    # start the tray app
```

With a standalone build, the `tokentray` CLI sits next to the app (inside
`tokentray.app/Contents/MacOS` on macOS).

## Alerts and polling

| Setting | Default | What it does |
|---|---|---|
| `poll_interval` | `120` | Seconds between usage checks (minimum 30) |
| `thresholds` | `50,25,10` | Remaining % that raises an alert |
| `remind_before` | `60,30,10` | Minutes before a reset to remind you |
| `popup.duration` | `8` | Seconds an alert card stays up |
| `popup.position` | `auto` | `bottom-right`, `top-right`, or `auto` (top on macOS, bottom elsewhere) |
| `native_notifications` | Windows `false`, others `true` | Also send OS notifications |

```bash
tokentray config set poll_interval 300    # check every 5 minutes
tokentray config set thresholds 50,20,5   # alert at 50%, 20% and 5% left
tokentray config set remind_before 30,10  # remind 30 and 10 minutes before reset
tokentray config get thresholds
```

Changes reach the running app straight away, except `poll_interval` and
`language`, which apply after a restart. `tokentray config path` shows where the
config file lives.

> [!TIP]
> Need some quiet? Choose **Pause alerts for 1 hour** in the tray menu. **Test
> notification** previews the alert cards with fresh data.

<details>
<summary><b>More settings and webhooks</b></summary>

| Setting | Default | What it does |
|---|---|---|
| `language` | from locale | `en` or `ko` |
| `webhook.enabled` / `webhook.kind` | `false` / `ntfy` | External alerts via `slack`, `discord`, `ntfy` or `generic` |
| `codex.refresh` | `false` | Let tokentray refresh the Codex token |
| `linux.force_xwayland` | `true` | See Platform notes |

Choose **Notification integrations…** in the tray menu to set up one webhook,
validate the URL and send a test, or use the terminal:

```bash
tokentray webhook setup --service slack
tokentray webhook test
```

The URL is kept in the OS keyring. Alerts are only sent while tokentray runs on
a device that is online; if several devices watch the same account, enable
webhooks on just one to avoid duplicates. For Slack, set
`packaging/resources/tokentray-512.png` as the app icon; Discord lets you set
the webhook avatar in the channel settings.

</details>

<details>
<summary><b>All commands</b></summary>

| Command | Description |
|---|---|
| `tokentray` | Start the tray app |
| `tokentray setup` | Interactive first-run configuration |
| `tokentray status` | Print current quota (asks the running app first) |
| `tokentray open` / `refresh` / `stop` | Control a running instance |
| `tokentray doctor` | Check credentials, keyring, tray and notification delivery |
| `tokentray config get/set/path` | Read and write settings |
| `tokentray state reset --welcome/--alerts/--all` | Re-arm the first-run notice or the alert memory |
| `tokentray webhook setup/test` | Configure and test a webhook |
| `tokentray autostart enable/disable/status` | Manage start-at-login |

</details>

## Platform notes

<details>
<summary><img src="https://img.shields.io/badge/Windows-0078D6?style=flat-square&logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0wIDBoMTEuNHYxMS40SDB6TTEyLjYgMEgyNHYxMS40SDEyLjZ6TTAgMTIuNmgxMS40VjI0SDB6TTEyLjYgMTIuNkgyNFYyNEgxMi42eiIvPjwvc3ZnPg%3D%3D" alt="Windows"></summary>

- A new tray icon may land among the hidden icons. The welcome card links to the
  taskbar setting, where the entry's name starts with `tokentray`.
- On the SmartScreen prompt for a standalone build, choose *More info* then
  *Run anyway*.
- Installed with uv or pip, the background process shows in Task Manager as
  `pythonw.exe`.

</details>

<details>
<summary><img src="https://img.shields.io/badge/macOS-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS"></summary>

- Builds are ad-hoc signed, not notarised. If Gatekeeper blocks the app:

  ```bash
  xattr -dr com.apple.quarantine /Applications/tokentray.app
  ```

- Apple silicon only. The app lives in the menu bar, so there is no Dock icon.
- The CLI is at `/Applications/tokentray.app/Contents/MacOS/tokentray`; symlink
  it onto your `PATH` to type `tokentray`.
- Reading Claude Code credentials from the login keychain may show an access
  prompt the first time.
- Notification Center delivery from a tray app is unreliable, so tokentray's own
  alert cards are the main channel. `tokentray doctor` shows what your build can do.

</details>

<details>
<summary><img src="https://img.shields.io/badge/Linux-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux"></summary>

- x86_64 tarball only. `./install.sh` adds a launcher entry and icon for your
  user; `./install.sh --uninstall` removes them.
- Qt needs a few system libraries that minimal installs, including stock Ubuntu
  24.04, may lack:

  ```bash
  sudo apt install libxcb-cursor0 libxkbcommon0 libegl1 libgl1 libdbus-1-3 libfontconfig1 libglib2.0-0
  ```

- GNOME needs the AppIndicator extension to show a tray icon; KDE works out of
  the box.
- On Wayland, tokentray runs through XWayland so alert cards can sit next to the
  tray. With `linux.force_xwayland = false` it runs natively, but the compositor
  decides where cards appear.
- Without a keyring service such as SecretService, secrets fall back to an
  owner-only local file, and setup tells you so.

</details>

## More details

<details>
<summary><b>Login credentials</b></summary>

tokentray reads the credentials Claude Code and Codex already saved:

| Service | Location |
|---|---|
| Claude Code | `~/.claude/.credentials.json` (or `$CLAUDE_CONFIG_DIR`), then the macOS login keychain |
| Codex | `~/.codex/auth.json` (or `$CODEX_HOME`) |

- **Log in** in the panel or an alert opens a terminal running the login command
  and watches for new credentials for up to five minutes. If no terminal can be
  opened, copy the command shown.
- Claude token refresh is left to Claude Code. Codex refresh is opt-in
  (`codex.refresh`) and re-reads `auth.json` before writing, so it never
  overwrites the Codex CLI.
- A token pasted during `setup` is stored in the OS keyring. A pasted Claude token
  cannot be renewed when it expires.
- `doctor` reporting `no token in file` does not always mean you are logged out:
  the file may hold plan metadata while sign-in is handled elsewhere.

</details>

<details>
<summary><b>How alerts are delivered</b></summary>

- **Windows** shows tokentray's own cards. Set `native_notifications = true` for
  Windows banners instead; if a banner cannot be submitted, the card is shown.
  Welcome and login-recovery alerts always use cards so their buttons work.
- **macOS and Linux** show cards and also send an OS notification.
- **Test notification** fetches fresh usage and shows one card per service. It
  does not touch alert history or send webhooks.
- Every OS notification attempt is logged; open the log from the tray menu.

</details>

## Privacy

> [!NOTE]
> No telemetry. Claude and Codex tokens are sent only to `api.anthropic.com`,
> `chatgpt.com` and `auth.openai.com` over HTTPS. Webhooks receive alert text,
> never tokens.

Caches and the fallback secret file are owner-only (`0600`) on macOS and Linux;
on Windows they inherit your user profile's permissions.

## Contributing

Bug reports, ideas and pull requests are welcome, in English or Korean.

- 🐛 **Found a bug?** Open a [bug report](https://github.com/messy-snail/tokentray/issues/new?template=bug_report.yml)
  with `tokentray --version` and `tokentray doctor` output.
- 💡 **Have an idea?** Open a [feature request](https://github.com/messy-snail/tokentray/issues/new?template=feature_request.yml).
- 🔒 **Security issue?** Report it privately - see [SECURITY.md].
- 🛠️ **Want to send code?** Start with [CONTRIBUTING.md].

## License

MIT - see [LICENSE]. Standalone builds bundle Qt through PySide6 (LGPLv3) as
dynamically linked libraries.

> [!NOTE]
> tokentray is a from-scratch Python reimplementation derived from
> [haomingkoo/claude-codex-monitor](https://github.com/haomingkoo/claude-codex-monitor)
> (MIT). It follows that project's quota endpoints, pace and burn-out formulas
> and colour tiers; its MIT notice is kept in [LICENSE].

<!-- Absolute, because this file is also the PyPI long description and a
     relative link there resolves against pypi.org. -->
[LICENSE]: https://github.com/messy-snail/tokentray/blob/main/LICENSE
[SECURITY.md]: https://github.com/messy-snail/tokentray/blob/main/SECURITY.md
[CONTRIBUTING.md]: https://github.com/messy-snail/tokentray/blob/main/CONTRIBUTING.md
