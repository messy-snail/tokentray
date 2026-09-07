# tokentray

A system-tray monitor for **Claude Code** and **OpenAI Codex** quota, with
readable desktop alerts before you run out. Windows, macOS and Linux.

> **Attribution.** tokentray is a from-scratch reimplementation, derived from
> [haomingkoo/claude-codex-monitor](https://github.com/haomingkoo/claude-codex-monitor)
> (MIT), which pioneered this idea as a SwiftBar plugin plus a PowerShell tray
> script. The quota endpoints, the pace/burnout formulas and the colour tiers
> follow that project so the numbers stay comparable. The original MIT notice is
> preserved in [LICENSE](LICENSE). Rewritten in Python so Windows, macOS and
> Linux share one codebase and one feature set.

## Status

Early development. The core (providers, computation, caching, CLI) is in place;
the tray UI, alerts and packaged builds are landing next.

## What it shows

- **Claude Code** - 5-hour session, 7-day window, per-model Opus/Sonnet
  sub-limits when in use, and pay-as-you-go Extra Usage.
- **Codex** - whichever rate-limit windows your plan actually reports (a
  weekly-only plan shows one `7d` row, not a mislabelled `5h` one), plus credits.
- For every window: remaining %, time to reset, **pace** (1.0x = exactly on
  track to last until reset) and a burnout projection.

## Install

```bash
uv tool install tokentray
```

Packaged builds for Windows, macOS and Ubuntu will be attached to each
[release](https://github.com/messy-snail/tokentray/releases).

## Use

```bash
tokentray status     # print current quota
tokentray doctor     # check credentials, keyring and tray availability
tokentray            # start the tray app
```

## How it finds your tokens

tokentray reads the credentials the CLIs already keep on your machine and
**never refreshes Claude's token** - Claude Code owns it, and a second writer is
how people get logged out. When it expires, tokentray says so and points you at
`claude`.

| | Location |
|---|---|
| Claude Code | `~/.claude/.credentials.json` (or `$CLAUDE_CONFIG_DIR`), falling back to the macOS login keychain |
| Codex | `~/.codex/auth.json` (or `$CODEX_HOME`) |

If a file holds no usable token - Claude Code writes plan metadata with a blank
`accessToken` when the session is authenticated elsewhere - `tokentray doctor`
reports `no token in file` rather than claiming you are logged out.

Codex token refresh is **opt-in** (`tokentray config set codex.refresh true`)
because it rewrites `auth.json`, a file the Codex CLI also owns. When enabled,
tokentray re-reads the file immediately before writing and backs off if the CLI
changed it in the meantime.

## Privacy

Your tokens go to their own vendor over HTTPS and nowhere else. The three hosts
tokentray contacts are `api.anthropic.com`, `chatgpt.com` and
`auth.openai.com`. There is no telemetry. Caches are written owner-only.

## Development

```bash
uv sync
uv run pytest
```

## License

MIT - see [LICENSE](LICENSE).
