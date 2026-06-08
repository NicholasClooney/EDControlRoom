# Project Status

_This is the startup handoff document for the repo. Keep it current, compact, and biased toward what the next session needs immediately._

Last updated: 2026-06-08

## Current Snapshot

- Plan 0001 (macOS MVP portability) is complete. The shared runtime, config system, journal parsing, bindings lookup, and synthetic input path are in place and live-validated on macOS + CrossOver.
- The project is in follow-up work, not a full autopilot rewrite. Active work is focused on journal-driven routines, two-way hauling, CV/capture validation, and operator diagnostics.
- `control_room.py` is the primary operator surface. `run_routine.py`, `ship_controls.py`, `diagnostics.py`, and the journal/bindings helpers are the main manual-validation tools.

## Active Capabilities

- Journal/runtime: journal tailing, bindings lookup, runtime construction, and shared platform seams are working.
- Routines: `jump`, `dock`, `undock`, market buy/sell, galaxy-map destination setting, throttle zeroing, and the current two-station haul loop all exist behind `edap/routines/`.
- Two-way haul startup now detects the active station/phase from journal position, `Cargo.json`, and `Market.json` fallback data, so a station-2 start no longer blindly runs station-1 actions first.
- Two-way haul transit resume now distinguishes “already dropped near destination” from “docking already requested/granted”: it skips the extra `SupercruiseExit` wait in the first case, and waits for `Docked` instead of re-requesting docking in the second.
- Two-way haul departures now auto-tap raw key `k` after mass lock clears to engage hyperspace FSD by default; `controls.haul_two_way_auto_hyperspace_engage` disables it when needed.
- Two-way haul transit now opens the left external panel on hyperspace arrival by default so the nav page is ready for station approach, after a configurable default 3-second delay; `controls.haul_two_way_open_nav_panel_after_hyperspace_arrival` and `controls.haul_two_way_nav_panel_open_delay_seconds` control that behavior.
- Control room: live Textual UI with ship status, market panel, haul stats, replay/history, persisted state, and routine dispatch.
- Control room: live Textual UI with ship status, market panel, haul stats, replay/history, persisted state, routine dispatch, and queued cross-platform TTS announcements for haul/navigation milestones.
- TTS/config: announcement IDs are typed in code, while default phrase text now lives in `defaults/tts.toml` and merges with user `config.toml` overrides under `[tts]`.
- Platform scope: macOS + CrossOver is the only live-validated operator path. Windows and Linux input/runtime paths exist with unit-test and CI coverage, but not live validation.
- CI: cross-platform unittest workflow exists in GitHub Actions, and a timing guard now enforces a 10-second ceiling on `tests/test_haul_loop.py`.

## Key Caveats

- The legacy autopilot loop is still not ported. This repo is currently automation/runtime tooling plus a growing set of journal-driven routines, not a complete autopilot.
- Two-way hauling is the active operator path, but it still needs more live validation around startup/resume/station-role detection after the latest fixes.
- TTS is implemented for macOS (`say`) plus Linux/Windows fallbacks, but only macOS is expected to be live-validated soon; wording/noise level still needs operator feedback after in-game use.
- CV is still at validation/scaffolding stage. Template matching has been re-baked against CrossOver captures, but there is no real continuous alignment loop yet.
- Timing enforcement is intentionally narrow for now: only `tests/test_haul_loop.py` has a hard runtime budget because it was the clear outlier.

## Current Next Steps

1. Live-validate the updated two-way haul startup path, especially station-2 starts and `Market.json` fallback behavior.
2. Live-test the new queued TTS callouts on macOS and trim or reword noisy announcements based on operator feedback.
3. Keep the timing guard in place and expand it only after measuring stable CI variance on other candidate suites.
4. Continue the next portability follow-up slice: CV capture/performance measurement, journal latency measurement, and diagnostics/dashboard work from plans 0002-0004.

## Handoff Links

- Rolling recent session notes: [session-log.md](session-log.md)
- Archive for detailed validation notes, longer capability status, and historical handoff detail: [status-archive.md](status-archive.md)
- Maintained plans: [plans/](plans/)
- Operator workflows: [operators/](operators/)
- Deeper research/history: [research/](research/) and [devlog/](devlog/)

## Maintenance Policy

- Keep this file high-signal only: current status, active capabilities, key caveats, immediate next steps, and minimal handoff context.
- Put short-lived session detail in [session-log.md](session-log.md). Keep that file at or under 20 lines. If a new entry would exceed the limit, append the full current log to [status-archive.md](status-archive.md), reset `session-log.md` to a fresh empty log template, then write the new entry.
- Put verbose validation logs, session chronology, long capability matrices, refactor TODOs, and speculative backlog notes in [status-archive.md](status-archive.md) or a more specific supporting doc.
- Do not read [status-archive.md](status-archive.md) during normal work unless the user explicitly asks for archive/history detail or newer compact docs are insufficient to unblock the task.
- If a section starts reading like a changelog or investigation log, move that detail out of `STATUS.md` and leave a one-line summary plus a link.
