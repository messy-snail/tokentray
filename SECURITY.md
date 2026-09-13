# Security policy

tokentray reads the login tokens that Claude Code and Codex store on your
machine, and can keep a webhook URL in the OS keyring or a fallback file. A
mistake in that handling can expose someone's account, so please report such
problems privately.

## Reporting a vulnerability

Use GitHub's private reporting:
[Report a vulnerability](https://github.com/messy-snail/tokentray/security/advisories/new).
Please do not open a public issue for it. Reports in English or Korean are both
fine.

Include the tokentray version, your operating system, and the steps to
reproduce. Leave real tokens and webhook URLs out; a description of where they
end up is enough.

You can expect a first reply within a week. Once a fix is released, the
advisory is published with credit to the reporter unless you would rather stay
anonymous.

## In scope

- Login tokens sent anywhere other than `api.anthropic.com`, `chatgpt.com` or
  `auth.openai.com`, or written to logs, caches or notifications.
- Webhook URLs or other secrets readable by other users: the keyring fallback
  file (`secrets.toml`) and the caches are meant to be owner-only (`0600`) on
  macOS and Linux.
- The local command socket or named pipe accepting commands from another user.
- Codex token refresh overwriting or corrupting the Codex CLI's `auth.json`.

Problems in Claude Code, Codex, their APIs, or the OS keyring itself should go
to those projects.

## Supported versions

Only the latest release receives security fixes.
