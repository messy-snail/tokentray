# Changelog

## 0.1.0 - unreleased

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
