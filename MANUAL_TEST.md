# Manual test checklist

**English** | [한국어](MANUAL_TEST.ko.md)

The automated suite runs headless, so it proves the code works, not that the
app looks or behaves right on a real desktop. Run this list on each platform
before tagging a release.

Legend: **W** Windows 11 · **M** macOS · **L** Ubuntu (both GNOME/Wayland and X11)

Some of this no longer needs a person. `tests/test_platform.py` covers the
autostart backends, both IPC transports and the Wayland plugin choice on every
CI runner, and `scripts/verify-linux.sh` covers items 19 (under `--gui`), 22, 27
and 30 plus the Qt library and Korean font prerequisites on a real Linux box.
Items 25 and 26 are not automated: nothing logs a CLI out or removes
`auth.json` for you. What is left below is what only eyes can settle: whether
the icon reads at 16 px, whether the toast landed in the right corner, whether
Korean text fits its box.

## Tray presence

| # | Check | W | M | L |
|---|---|---|---|---|
| 1 | Icon appears within ~10 s of launch. On Windows also confirm it in the overflow flyout, since new icons hide there by default. | ☐ | ☐ | ☐ |
| 2 | Icon colour matches the lowest remaining window (green >50, amber 21-50, red ≤20). | ☐ | ☐ | ☐ |
| 3 | With both providers configured, there are two concentric rings - Claude outside, Codex inside - and each drains clockwise from the top. | ☐ | ☐ | ☐ |
| 3a | With one provider disabled or unconfigured, the other keeps its ring position and the empty one stays a grey track; the icon does not collapse to a single fat ring. | ☐ | ☐ | ☐ |
| 3b | A provider at 0% keeps a short coloured tick at the top, so it reads differently from one with no data at all. | ☐ | ☐ | ☐ |
| 4 | Hovering shows a tooltip with each window's remaining percentage. The tooltip starts with `tokentray`, which is also the entry's name under Settings > Personalization > Taskbar > Other system tray icons on Windows. | ☐ | ☐ | ☐ |
| 5 | Right-click (Windows/Linux) or click (macOS) opens the menu; every entry is present and in the selected language. | ☐ | ☐ | ☐ |
| 6 | Left-click opens the detail panel (Windows/Linux). | ☐ | n/a | ☐ |
| 7 | Clicking outside the panel dismisses it. | ☐ | ☐ | ☐ |

## Notifications

| # | Check | W | M | L |
|---|---|---|---|---|
| 8 | "Test notification" disables the menu while fetching fresh usage, then shows Claude Code and Codex cards with a labelled meter per limit matching the updated panel. Repeated requests produce one preview; failures have no meters and cached values are marked as previous data. Automatic alert history and webhooks are unaffected. | ☐ | ☐ | ☐ |
| 8a | Windows defaults to custom cards with no OS banner. Explicitly enabling native notifications instead sends one text summary banner. Linux/macOS keep the custom card plus the optional system notification. On macOS an ad-hoc signed `.app` does deliver the banner; running outside a bundle does not, so check **Open log** for the attempt. | ☐ | ☐ | ☐ |
| 9 | The toast does **not** steal focus - keep typing in an editor while it appears and confirm no keystrokes are lost. | ☐ | ☐ | ☐ |
| 10 | It fades out on its own after ~8 s, and hovering it stops that countdown. | ☐ | ☐ | ☐ |
| 11 | Clicking the toast opens the detail panel. | ☐ | ☐ | ☐ |
| 12 | Two toasts stack without overlapping; dismissing the lower one slides the other down. | ☐ | ☐ | ☐ |
| 13 | The toast lands on the screen holding the tray icon in a multi-monitor setup. | ☐ | ☐ | ☐ |
| 14 | "Pause alerts for 1 hour" silences toasts; the menu entry flips to "Resume". | ☐ | ☐ | ☐ |
| 14a | Open "Notification integrations…" and check the warning icon and notification requirements in English and Korean at the minimum window width (440 logical pixels). Text must wrap without clipping or overlapping fields or buttons. Confirm the notice remains visible with external alerts disabled, after changing services, and after test success or failure. | ☐ | ☐ | ☐ |
| 14b | Change the selected service and confirm the old URL is cleared, a new URL is required, and saving applies without restarting tokentray. | ☐ | ☐ | ☐ |
| 14c | Step through all four services and confirm each shows its own numbered steps, that the links open, and that the format line reads out the placeholders in full - `<id>`/`<token>` must not be swallowed as HTML. Generic shows no format line. | ☐ | ☐ | ☐ |

## External delivery verification

Verify each service on one available platform. Keep these results separate from
the OS-specific UI and secret-storage checks above. Mock HTTP tests verify
request construction and error handling; they do not establish real delivery.

| Service | Real delivery status | Evidence / remaining checks |
|---|---|---|
| Discord | Receipt confirmed by the maintainer (reported 2026-09-10) | OS, build and message scenarios were not specified. Confirm Korean text and the layout of a usage alert separately. |
| Slack | Not verified | Send a test and a usage alert; check receipt, Korean text and message layout. |
| ntfy | Not verified | Send a test and a usage alert; check receipt, Korean text and message layout in the subscribed client. |
| Generic | Endpoint-specific; not verified | Check the JSON request and receiving application's handling against a controlled endpoint. |

Record the OS, build and scenarios when completing a real-service check. A
successful test message does not by itself verify threshold or reset reminders.

## Appearance

| # | Check | W | M | L |
|---|---|---|---|---|
| 14d | With `native_notifications false`, custom cards appear at the top on macOS and the bottom elsewhere by default. Set `popup.position` to `bottom-right` then `top-right`, each followed by "Test notification": the card moves without a restart and stays at the right edge. Restore native notifications afterward. OS banner placement is system-controlled. | ☐ | ☐ | ☐ |
| 15 | Switch the OS between light and dark, restart, and confirm the toast and panel follow. | ☐ | ☐ | ☐ |
| 15a | Windows only: set Colours to Custom with Windows mode Dark and app mode Light, then the reverse. The tray icon - including the faint ring before the first poll - stays visible on the taskbar while the panel follows the app mode. | ☐ | n/a | n/a |
| 16 | Switch the language in the tray menu; the menu, panel and next toast are all translated. | ☐ | ☐ | ☐ |
| 17 | Korean text renders without missing glyphs or clipping. | ☐ | ☐ | ☐ |
| 17a | Window names use one scheme everywhere: `5 hours` / `7 days` / `7 days · Opus`, never a mix of `5-Hour Session` and `Codex 7d`. The tooltip is the only place abbreviations appear, and a sub-limit keeps its duration there (`5h·Spark`, not `Spark` twice). | ☐ | ☐ | ☐ |
| 17b | The panel title names the plan as a product, e.g. `Codex (Pro Lite)` rather than `Codex (prolite)`. | ☐ | ☐ | ☐ |

## Lifecycle

| # | Check | W | M | L |
|---|---|---|---|---|
| 18 | Launching a second time raises the panel instead of adding a second icon. The terminal says it is already running, with the pid and, on Windows, where hidden tray icons live. | ☐ | ☐ | ☐ |
| 19 | `tokentray status` in a terminal reports data from the running app and prints its pid. On macOS and Linux the CLI is `dist/tokentray/tokentray`, or `tokentray.app/Contents/MacOS/tokentray` inside the bundle. | ☐ | ☐ | ☐ |
| 20 | On a Korean or Japanese Windows console (cp949/cp932), `tokentray status` prints without a UnicodeEncodeError. | ☐ | n/a | n/a |
| 21 | Enable start-at-login, log out and back in, and confirm it starts with no console window and no welcome toast. | ☐ | ☐ | ☐ |
| 22 | Disable it and confirm the registration is gone (`tokentray autostart status`). | ☐ | ☐ | ☐ |
| 22a | With the app running, `tokentray config set native_notifications false`, then "Test notification": the toasts still appear and no OS banner does. Set it back to `true` and confirm the banner returns - all without restarting. | ☐ | ☐ | ☐ |
| 23 | Quit from the menu and confirm the process exits and the tray icon disappears. | ☐ | ☐ | ☐ |
| 23a | With the app running, `tokentray state reset --welcome`, wait past one poll interval, then quit and relaunch: the welcome appears again. This proves the running app's in-memory state did not overwrite the reset. | ☐ | ☐ | ☐ |

## Failure states

| # | Check | W | M | L |
|---|---|---|---|---|
| 24 | Disconnect the network: the panel keeps the last numbers and marks them stale rather than blanking. | ☐ | ☐ | ☐ |
| 25 | Log out of one CLI: that provider reports "login expired" with the command to fix it, once, not on every poll. | ☐ | ☐ | ☐ |
| 26 | Remove `~/.codex/auth.json`: Codex reports not logged in and Claude keeps working. | ☐ | ☐ | ☐ |
| 27 | `tokentray doctor` reports credentials, keyring backend, tray availability and the `native alerts` / `app bundle` lines correctly. It also prints `running yes (pid N)` while the app is up and, on Windows, the hidden-icons hint. | ☐ | ☐ | ☐ |

## Connections and login recovery

| # | Check | W | M | L |
|---|---|---|---|---|
| 27a | A provider whose credentials expired shows a **Log in** button in the detail panel and on the card; pressing it runs `claude auth login` or `codex login` in a new terminal window. On macOS the first attempt raises the Automation prompt for controlling Terminal, once. | ☐ | ☐ | ☐ |
| 27b | Finishing the login in that terminal is picked up within five minutes: the provider says the credentials changed and usage is fetched again. After five minutes it says it stopped waiting. | ☐ | ☐ | ☐ |
| 27c | While waiting, **Check again** and **Stop waiting** are offered, and stopping does not close the terminal the user opened. Signing in later and refreshing still works. | ☐ | ☐ | ☐ |
| 27d | When the terminal cannot be opened - including denying the macOS Automation prompt - **Copy command** and **Log in** are offered and the copied command lands on the clipboard. When the CLI is not found, **Installation guide** and **Check again** are offered, and the guide only opens the official docs; it installs nothing. | ☐ | ☐ | ☐ |
| 27e | `tokentray setup` asks for the language first, then reports CLI discovery and credential state separately per provider. A token that was found but not verified reads "Found; connection unverified". Log in, installation guide, recheck, skip, pasted token and disable all work, and start-at-login is the last question. | ☐ | ☐ | ☐ |
| 27f | Refreshing from the detail panel disables the button and shows the loading state, then a success or failure result. Pressing it repeatedly does not stack up fetches. | ☐ | ☐ | ☐ |

## Linux specifics

| # | Check | |
|---|---|---|
| 28 | Under a Wayland session, confirm the app runs through XWayland by default and the toast is positioned in the corner. | ☐ |
| 29 | Set `linux.force_xwayland = false`, restart under Wayland, and confirm the app runs natively (no XWayland), alert cards still appear (placement is up to the compositor), and with `native_notifications` on the OS notification is delivered too. | ☐ |
| 30 | With no SecretService running (`env -u DBUS_SESSION_BUS_ADDRESS`), `tokentray setup` falls back to the owner-only file and says so. | ☐ |
| 31 | Works on both GNOME (with the AppIndicator extension) and KDE. | ☐ |

## macOS specifics

| # | Check | |
|---|---|---|
| 32 | Claude Code keeps its login in the login keychain rather than a file. The first read either succeeds or raises the keychain authorization prompt. Choosing **Deny** must not quit the app; the provider must say the keychain could not be read - not that you are logged out - and offer **Check again**. | ☐ |
| 33 | After a denial, neither the poll (120 s by default) nor the two-second login probe brings the prompt back. Only **Refresh now** or **Check again** asks again. | ☐ |
| 34 | The `.app` shows the double-ring icon in Finder - not a generic placeholder. The Gatekeeper block dialog uses a system warning icon rather than the app's, so do not look for it there. | ☐ |
| 35 | Downloaded from a release, the bundle is quarantined and launching it raises the block dialog; confirm `xattr -d com.apple.quarantine` is what unblocks it. Setting the attribute by hand on a copy of a local build reproduces both halves, but the real download path still needs a release. | ☐ |
| 36 | Claude credentials are read through the `security` command, so the keychain ACL is evaluated for that tool rather than for the bundle. Confirm a freshly rebuilt bundle does not raise the authorization prompt again. | ☐ |
| 37 | With a menu bar manager running (Bartender, Ice, Hidden Bar), confirm the welcome toast carries the line about unhiding tokentray - and that the icon is findable once unhidden. Managers hide new items by default, which is how a working app reads as a broken one. | ☐ |
| 37a | `tokentray doctor` run from inside the `.app` and from a checkout report different `app bundle` lines (a path plus `ad-hoc`, versus `none`), and both print the Notification Centre consequence. | ☐ |

## What the checklist cannot reach

- **Gatekeeper** (item 35) only triggers on a downloaded artifact. A local
  `pyinstaller` build is never quarantined, so this waits for the first tagged
  release.
- **Item 21** needs a real log out and back in on each OS; nothing simulates it.
- **Item 31** needs two Linux desktops, not two distributions - GNOME with the
  AppIndicator extension and KDE - because their tray hosts are different
  implementations and a pass on one says nothing about the other.
