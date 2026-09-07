# Manual test checklist

The automated suite runs headless, so it proves the code works, not that the
app looks or behaves right on a real desktop. Run this list on each platform
before tagging a release.

Legend: **W** Windows 11 · **M** macOS · **L** Ubuntu (both GNOME/Wayland and X11)

## Tray presence

| # | Check | W | M | L |
|---|---|---|---|---|
| 1 | Icon appears within ~10 s of launch. On Windows also confirm it in the overflow flyout, since new icons hide there by default. | ☐ | ☐ | ☐ |
| 2 | Icon colour matches the lowest remaining window (green >50, amber 21-50, red ≤20). | ☐ | ☐ | ☐ |
| 3 | With both providers configured, the ring is split - Claude on the left half, Codex on the right. | ☐ | ☐ | ☐ |
| 4 | Hovering shows a tooltip with each window's remaining percentage. | ☐ | ☐ | ☐ |
| 5 | Right-click (Windows/Linux) or click (macOS) opens the menu; every entry is present and in the selected language. | ☐ | ☐ | ☐ |
| 6 | Left-click opens the detail panel (Windows/Linux). | ☐ | ☐ | n/a |
| 7 | Clicking outside the panel dismisses it. | ☐ | ☐ | ☐ |

## Notifications

| # | Check | W | M | L |
|---|---|---|---|---|
| 8 | "Test notification" shows a toast in the corner: rounded card, tier-coloured stripe, progress meter, readable at a glance. | ☐ | ☐ | ☐ |
| 9 | The toast does **not** steal focus - keep typing in an editor while it appears and confirm no keystrokes are lost. | ☐ | ☐ | ☐ |
| 10 | It fades out on its own after ~8 s, and hovering it stops that countdown. | ☐ | ☐ | ☐ |
| 11 | Clicking the toast opens the detail panel. | ☐ | ☐ | ☐ |
| 12 | Two toasts stack without overlapping; dismissing the lower one slides the other down. | ☐ | ☐ | ☐ |
| 13 | The toast lands on the screen holding the tray icon in a multi-monitor setup. | ☐ | ☐ | ☐ |
| 14 | "Pause alerts for 1 hour" silences toasts; the menu entry flips to "Resume". | ☐ | ☐ | ☐ |

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
| 19 | `tokentray status` in a terminal reports data from the running app and prints its pid. | ☐ | ☐ | ☐ |
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
