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
- Raised the default undock `NoTrack`/clear-station timeout to 600 seconds and changed two-way haul departures to abort, log, and announce a resumable stop instead of continuing blind after the timeout.
- Shortened default TTS jump/arrival phrases to avoid speaking long system names: "Jumping to the next system." and "Arrived."
- Shortened the haul-aborted TTS line to just "Haul aborted." and moved the recovery guidance into the haul log message: `replay / ctrl-r`.
- Fixed the control-room HAUL panel regression from the one-way -> two-way transition: cycle profit/time now follow the two-way station flow, finalize on the return sale at station 1, and carry the next run's station-1 buy cost into the clean departure instead of dropping it.
- Fixed control-room haul launch wiring so the configured `undock_no_track_timeout_seconds=600` reaches `haul_loop_two_way`; the live NoTrack progress line no longer falls back to the stale `60s` default.
