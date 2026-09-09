# Manual test checklist

The automated suite runs headless, so it proves the code works, not that the
app looks or behaves right on a real desktop. Run this list on each platform
before tagging a release.

Legend: **W** Windows 11 · **M** macOS · **L** Ubuntu (both GNOME/Wayland and X11)

Some of this no longer needs a person. `tests/test_platform.py` covers the
autostart backends, both IPC transports and the Wayland plugin choice on every
CI runner, and `scripts/verify-linux.sh` covers items 19, 22, 25-27 and 30 plus
the Qt library and Korean font prerequisites on a real Linux box. What is left
below is what only eyes can settle: whether the icon reads at 16 px, whether the
toast landed in the right corner, whether Korean text fits its box.

## Tray presence

| # | Check | W | M | L |
|---|---|---|---|---|
| 1 | Icon appears within ~10 s of launch. On Windows also confirm it in the overflow flyout, since new icons hide there by default. | ☐ | ☐ | ☐ |
| 2 | Icon colour matches the lowest remaining window (green >50, amber 21-50, red ≤20). | ☐ | ☐ | ☐ |
| 3 | With both providers configured, there are two concentric rings - Claude outside, Codex inside - and each drains clockwise from the top. | ☐ | ☐ | ☐ |
| 3a | With one provider disabled or unconfigured, the other keeps its ring position and the empty one stays a grey track; the icon does not collapse to a single fat ring. | ☐ | ☐ | ☐ |
| 3b | A provider at 0% keeps a short coloured tick at the top, so it reads differently from one with no data at all. | ☐ | ☐ | ☐ |
| 4 | Hovering shows a tooltip with each window's remaining percentage. | ☐ | ☐ | ☐ |
| 5 | Right-click (Windows/Linux) or click (macOS) opens the menu; every entry is present and in the selected language. | ☐ | ☐ | ☐ |
| 6 | Left-click opens the detail panel (Windows/Linux). | ☐ | ☐ | n/a |
| 7 | Clicking outside the panel dismisses it. | ☐ | ☐ | ☐ |

## Notifications

| # | Check | W | M | L |
|---|---|---|---|---|
| 8 | "Test notification" shows separate Claude Code and Codex toasts, each with the tokentray ring, provider name, tier-coloured stripe and progress meter. | ☐ | ☐ | ☐ |
| 9 | The toast does **not** steal focus - keep typing in an editor while it appears and confirm no keystrokes are lost. | ☐ | ☐ | ☐ |
| 10 | It fades out on its own after ~8 s, and hovering it stops that countdown. | ☐ | ☐ | ☐ |
| 11 | Clicking the toast opens the detail panel. | ☐ | ☐ | ☐ |
| 12 | Two toasts stack without overlapping; dismissing the lower one slides the other down. | ☐ | ☐ | ☐ |
| 13 | The toast lands on the screen holding the tray icon in a multi-monitor setup. | ☐ | ☐ | ☐ |
| 14 | "Pause alerts for 1 hour" silences toasts; the menu entry flips to "Resume". | ☐ | ☐ | ☐ |
| 14a | Open "Notification integrations…", configure one Slack or Discord webhook, and confirm "Send test" reaches only that destination with the correct provider-style layout. | ☐ | ☐ | ☐ |
| 14b | Change the selected service and confirm the old URL is cleared, a new URL is required, and saving applies without restarting tokentray. | ☐ | ☐ | ☐ |

## Appearance

| # | Check | W | M | L |
|---|---|---|---|---|
| 15 | Switch the OS between light and dark, restart, and confirm the toast and panel follow. | ☐ | ☐ | ☐ |
| 16 | Switch the language in the tray menu; the menu, panel and next toast are all translated. | ☐ | ☐ | ☐ |
| 17 | Korean text renders without missing glyphs or clipping. | ☐ | ☐ | ☐ |

## Lifecycle

| # | Check | W | M | L |
|---|---|---|---|---|
| 18 | Launching a second time raises the panel instead of adding a second icon. | ☐ | ☐ | ☐ |
| 19 | `tokentray status` in a terminal reports data from the running app and prints its pid. On macOS and Linux the CLI is `dist/tokentray/tokentray`, or `tokentray.app/Contents/MacOS/tokentray` inside the bundle. | ☐ | ☐ | ☐ |
| 20 | On a Korean or Japanese Windows console (cp949/cp932), `tokentray status` prints without a UnicodeEncodeError. | ☐ | n/a | n/a |
| 21 | Enable start-at-login, log out and back in, and confirm it starts with no console window and no welcome toast. | ☐ | ☐ | ☐ |
| 22 | Disable it and confirm the registration is gone (`tokentray autostart status`). | ☐ | ☐ | ☐ |
| 23 | Quit from the menu and confirm the process exits and the tray icon disappears. | ☐ | ☐ | ☐ |

## Failure states

| # | Check | W | M | L |
|---|---|---|---|---|
| 24 | Disconnect the network: the panel keeps the last numbers and marks them stale rather than blanking. | ☐ | ☐ | ☐ |
| 25 | Log out of one CLI: that provider reports "login expired" with the command to fix it, once, not on every poll. | ☐ | ☐ | ☐ |
| 26 | Remove `~/.codex/auth.json`: Codex reports not-configured and Claude keeps working. | ☐ | ☐ | ☐ |
| 27 | `tokentray doctor` reports credentials, keyring backend and tray availability correctly. | ☐ | ☐ | ☐ |

## Linux specifics

| # | Check | |
|---|---|---|
| 28 | Under a Wayland session, confirm the app runs through XWayland by default and the toast is positioned in the corner. | ☐ |
| 29 | Set `linux.force_xwayland = false`, restart under Wayland, and confirm it degrades to the notification-centre path instead of misplacing toasts. | ☐ |
| 30 | With no SecretService running (`env -u DBUS_SESSION_BUS_ADDRESS`), `tokentray setup` falls back to the owner-only file and says so. | ☐ |
| 31 | Works on both GNOME (with the AppIndicator extension) and KDE. | ☐ |

## macOS specifics

| # | Check | |
|---|---|---|
| 32 | Claude Code stores its credentials in the login keychain rather than a file. Confirm the first read either succeeds silently or raises a keychain authorization prompt - and that clicking **Deny** degrades the provider to an error line instead of crashing the app. | ☐ |
| 33 | After denying, confirm the prompt does **not** return on every poll (default 120 s). A modal every two minutes from an app with no Dock icon is unusable. | ☐ |
| 34 | The `.app` shows the double-ring icon in Finder and in the Gatekeeper dialog - not a generic placeholder. | ☐ |
| 35 | Downloaded from a release (not built locally), the bundle is quarantined; confirm `xattr -dr com.apple.quarantine` is what unblocks it, since a locally built `.app` carries no quarantine flag and cannot test this. | ☐ |
| 36 | Ad-hoc signatures change on every rebuild, which invalidates the keychain ACL. After installing an update, confirm the keychain prompt returning once is the worst that happens. | ☐ |
| 37 | With a menu bar manager running (Bartender, Ice, Hidden Bar), confirm the welcome toast carries the line about unhiding tokentray - and that the icon is findable once unhidden. Managers hide new items by default, which is how a working app reads as a broken one. | ☐ |

## What the checklist cannot reach

- **Gatekeeper** (item 35) only triggers on a downloaded artifact. A local
  `pyinstaller` build is never quarantined, so this waits for the first tagged
  release.
- **Item 21** needs a real log out and back in on each OS; nothing simulates it.
- **Item 31** needs two Linux desktops, not two distributions - GNOME with the
  AppIndicator extension and KDE - because their tray hosts are different
  implementations and a pass on one says nothing about the other.
