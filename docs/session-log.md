# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-11

- Added an `AGENTS.md` rule to use `gh` commands by default for GitHub work in this repo and recorded the policy pointer in `docs/STATUS.md`.
- Added operator-facing Control Room failure surfacing plus configurable default error-message templates in `defaults/error_messages.toml`, wired through `AppConfig.error_messages`, and rechecked the full suite at `361 tests in 0.169s`.
- Rebased `codex/session-error-message-overhaul` onto `dev`, resolved the maintained handoff-doc conflicts by preserving the configurable error-template status notes, and rechecked the full suite after the linear-history update.
