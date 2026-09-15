# Changelog

## 0.1.1 - 2026-09-15

### Fixed
- Respect request-limit waiting periods when refreshing usage, and report refresh
  results per service so a failure in one does not hide another service's result.
- Improve network diagnostics and distinguish waiting, cached data and failed
  refreshes in the detail panel.
- Launch the tray application independently of the terminal so closing the
  terminal does not stop it.
- Disable Windows' extra rectangular shadow around the transparent detail panel
  and notification windows while keeping the cards' own soft shadows.

## 0.1.0 - 2026-09-14

First release. A cross-platform reimplementation of
[haomingkoo/claude-codex-monitor](https://github.com/haomingkoo/claude-codex-monitor)
(MIT), whose macOS and Windows scripts had drifted apart; here both platforms
run the same code.

### Added
- Tray icon showing Claude Code and Codex remaining quota as concentric rings.
- Self-drawn toast notifications at 50/25/10% remaining, plus reset reminders.
- Detail panel with per-window meters, reset countdown, pace and burnout.
- `status`, `setup`, `doctor`, `open`, `refresh`, `stop`, `config`, `autostart`.
- Start-at-login on Windows, macOS and Linux, registering the GUI entry point.
- Single-instance enforcement with a local command socket.
- English and Korean, chosen from the desktop locale on first run.
- Optional Slack, Discord, ntfy or generic webhook delivery, configurable from
  the tray with URLs kept in the OS keyring.
- Provider-labelled notifications with the tokentray ring icon, so Claude Code
  and Codex alerts can be identified at a glance.
- `state reset` for re-arming the first-run notice and the alert memory, applied
  through the running instance so its in-memory copy cannot overwrite it.
- `doctor` reports whether OS notification delivery stands any chance here: the
  `.app` bundle, its signature, and what that means on macOS.
- Every OS notification attempt is logged, so a channel that drops them silently
  leaves evidence instead of nothing.
- "Test notification" now fires the OS notification centre alongside the in-app
  toast, so a dead native channel can be told from one nobody called.
- `config set` hands the change to a running instance, so thresholds, reminders,
  popup position and duration, and `native_notifications` no longer wait for a
  restart.
- `popup.position` now works. It was listed in the defaults, written into every
  config file and read by nothing; `auto`, `bottom-right` and `top-right` are
  honoured, and the `off` it used to offer is gone - it never did anything, so a
  config still carrying it keeps behaving as before.
- Launching `tokentray` while it is already running now says so, with the
  running pid and, on Windows, where hidden tray icons live. It used to exit
  without a word, which reads exactly like a failed start. `doctor` reports the
  running instance too.
- The tray tooltip always leads with `tokentray`, so the entry can be found in
  Windows' "Other system tray icons" settings, where it is otherwise a python.exe.
- On Windows the tray icon follows the taskbar's colour mode instead of the apps'
  mode, so light apps on a dark taskbar no longer paint a ring that all but vanishes.

### Fixed
- The self-drawn card stayed hidden on macOS whenever another app was frontmost.
  A Qt::Tool window is an NSPanel that the OS hides on deactivation - exactly
  when an alert is worth seeing, and outside an app bundle macOS delivers no
  banner, so the card may be the only channel.
- Switching language left the detail panel half-translated until the next poll.
  The views carry already-translated text, so the switch now rebuilds them from
  the last snapshots instead of re-rendering what was already worded.
- Stacked cards overlapped by the height of a menu bar. The top slot asked for a
  position above the work area - the transparent shadow margin is wider than the
  edge inset - and macOS answered by sliding that window back down, while the
  cards below were still spaced from the position nothing ever had.
- Hovering a card no longer let it expire under the cursor. Qt reports Leave when
  the pointer crosses onto a child widget, so settling on the card body counted
  as leaving and restarted the eight seconds.
- On Windows, `status`, `config set` and a second launch could now and then fail
  to hear back from the running app. The app hung up right after answering, and
  closing the server end of a named pipe throws away bytes the client has not
  read yet; it now waits for the client to hang up first.
- "Refresh now" reported failure whenever one service was not signed in, so
  anyone using only Claude Code or only Codex saw "Refresh failed" on every
  click. A service nobody signed in to no longer counts against the result.
- Closing "Notification integrations…" left its menu item dead until restart.
  The dialog deletes itself on close; the controller kept the stale wrapper, so
  the next open raised inside the slot and silently did nothing.
- A refused Claude Code keychain read was retried on every poll and on every
  two-second login probe, each call able to bring the authorization prompt back,
  and it was shown as "not logged in". It now says the keychain could not be
  read and asks again only when you refresh or press Check again. At launch the
  first poll and the login probe also read it at the same moment, so a denied
  keychain could ask twice before either saw the refusal; those reads now wait
  for each other.

### Differences from the reference implementation
- Alerts cover every window, including Codex and the per-model sub-limits;
  upstream alerted only on Claude's two windows.
- A sharp drop reports the worst threshold crossed instead of stepping down one
  level per poll, which delayed an "almost out" warning by several minutes.
- "Still working?" is measured as a usage delta between polls. Upstream compared
  pace against 1.3x, which its own 60/30/10-minute reminder defaults can never
  satisfy - exceeding 1.3x needs at least 23% of the window still to run.
- Backoff is stored as an explicit timestamp rather than by touching the cache
  file's mtime, so a suppressed failure is distinguishable from a fresh success.
- Claude's OAuth token is never refreshed by tokentray; Codex refresh is opt-in
  and re-checks the file before writing so it cannot clobber the Codex CLI.
- A missing seven-day window no longer blanks the display, and Codex window
  labels follow the API-reported duration.
