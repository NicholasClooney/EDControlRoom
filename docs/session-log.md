# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-08

- Two-way haul startup now infers the active station/phase from journal position, `Cargo.json`, and `Market.json` fallback data. Added regression coverage for station-2 startup cases.
- Added test timing guardrails: `tools/check_test_timing.py`, CI guard for `tests/test_haul_loop.py`, and support for both single-target and full-suite `unittest discover` timing checks.
- Trimmed `docs/STATUS.md` into a compact handoff document and moved long-form status/history into `docs/status-archive.md`.
- Two-way haul now taps raw `k` after mass-lock escape by default to engage hyperspace FSD; added `controls.haul_two_way_auto_hyperspace_engage` to disable that behavior per config.
- Two-way haul now opens the left external/nav panel on hyperspace arrival by default, with buffered journal handoff into docking so arrival detection does not consume `SupercruiseExit`/`Docked` events.
- Added `controls.haul_two_way_nav_panel_open_delay_seconds` with a default 3.0-second wait before the post-jump nav-panel open.
- Added queued TTS announcements for haul/control-room milestones, with typed announcement IDs in code and repo-shipped default phrases in `defaults/tts.toml` merged with user `[tts]` overrides from `config.toml`.
