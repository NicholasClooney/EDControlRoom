# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-11

- Added a standalone `multi_leg_haul` / `mult` control-room path plus `edap.routines.haul_multi_leg`: it loads either the new EDControlRoom multi-leg JSON schema or a Spansh result payload, derives stop/phase from live journal + cargo + market state, and keeps the existing two-way `haul` flow untouched; full suite green at `360 tests in 0.135s`.

## 2026-06-10

- Raised the GitHub Actions `test_timing` guard in `.github/workflows/tests.yml` from `3s` to `5s` so current CI runs stop failing on suite wall-clock jitter, and rechecked the full suite at `363 tests in 0.441s` with the timing report still topping out at `0.005s` per test.
- Added an `AGENTS.md` rule to use `gh` commands by default for GitHub work in this repo and recorded the policy pointer in `docs/STATUS.md`.
- Added operator-facing Control Room failure surfacing plus configurable default error-message templates in `defaults/error_messages.toml`, wired through `AppConfig.error_messages`, and rechecked the full suite at `361 tests in 0.169s`.
- Rebased `codex/session-error-message-overhaul` onto `dev` and resolved the maintained handoff-doc overlap by keeping both the configurable error-template note and the new GitHub `gh` policy note.
- Split Control Room default text into YAML assets (`defaults/error_messages.yaml` for paired failures plus `defaults/messages.yaml` for non-error text), kept `config.toml` overrides and legacy flat error keys loading, and rechecked the full suite at `363 tests in 0.437s`; timing report showed no individual test above `0.005s`.
