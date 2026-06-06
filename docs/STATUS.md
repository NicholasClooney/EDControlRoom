# Project Status

_This is the maintained status document for the repo. Update it at the end of each session when project understanding, port status, or next steps change. Keep it current over time rather than treating it as a frozen checkpoint._

Last updated: 2026-06-05 (session 2)

## Where We Are

Plan 0001 (macOS MVP portability) is complete. The four hard platform problems are proven on the current macOS + CrossOver setup:

- Journal auto-detection and parsing works against a real log.
- Bindings XML parsing and action lookup works.
- Screen capture from the CrossOver window works.
- Synthetic key input via Quartz `CGEventPost` reaches the game, including modifier combos and punctuation keys that broke the earlier `osascript` backend.

A shared runtime context, config system, bindings lookup seam, and a small runtime action surface are wired up. Utility scripts `diagnostics.py`, `ship_controls.py`, `check_bindings.py`, `set_binding.py`, `view_bindings.py`, `watch_journal.py`, and `run_routine.py` all work.

The first journal-driven runtime pieces now exist:

- `JournalWatcher` tails the latest `Journal.*` file incrementally, starts at end-of-file by default, and rolls over to newer journal files.
- `auto_zero_throttle_on_arrival` exists as the first watcher-to-controls routine and dispatches `SetSpeedZero` on `SupercruiseExit`.
- `jump` now exists as the first retrying journal-driven routine. It dispatches `HyperSuperCombination`, waits for `StartJump` / hyperspace start, then waits to re-enter `in_supercruise` and zeroes throttle.
- `dock` now exists as a journal-driven station approach routine. It can wait for `SupercruiseExit`, send the legacy docking-request menu walk, wait for docking journal events, and optionally chain the in-station refuel menu.
- `undock` now exists as a journal-driven routine. It sends `UI_Back x10`, `HeadLookReset`, a single `UI_Down` tap, and `UI_Select` to trigger launch, then polls for the `Undocked` journal event (configurable timeout, default 30s). The legacy `SetSpeedZero` calls between launch confirm and undock completion were dropped — the ship is still in the docking bay at that point and throttle state is irrelevant. Discrepancy noted in `docs/plans/0003-journal-driven-routines.md`.
- `run_routine.py` now supports `auto_zero_throttle_on_arrival`, `jump`, `dock`, `station_refuel_menu`, and `undock` as live manual harnesses for exercising journal-driven paths against a real Elite session.
- `run_routine.py` now emits live progress to stderr (waiting-for-event, event-detected, key-presses, pauses). JSON output is opt-in via `--json`.
- The current live manual test flows for those harnesses are documented in `docs/manual-journal-routine-testing.md`.

Latest live validation on the current macOS + CrossOver setup:

- raw key injection through `diagnostics.py --send-test-key` was re-validated after restoring macOS Accessibility permission for the terminal app
- `watch_journal.py` confirmed live journal tailing and the expected event vocabulary
- `run_routine.py --routine jump --log-events` captured the expected hyperspace sequence: `StartJump` with `JumpType == "Hyperspace"` followed by `FSDJump`
- `run_routine.py --routine dock --skip-supercruise-exit --auto-refuel --log-events` completed a full dock-and-refuel cycle; live testing revealed a retry-after-grant bug (watcher offset primed too late when supercruise wait is skipped) which was fixed in `edap/routines.py`
- Dock routine was further extended (not yet live-validated): boost after SupercruiseExit with configurable settle time, DockingDenied retry loop with configurable delay, `ui_left` after `ui_select` to dismiss the station contact menu
- `run_routine.py --routine undock --log-events` completed a full undock cycle from a docked state

The important caveat is that the real autopilot loop is still largely unported. The project is in a portability-first and runtime-seams phase, not a "macOS autopilot feature complete" phase.

## Port Status

| Capability | Status | Notes |
| --- | --- | --- |
| Journal parsing | Done | `edap/state.py` — tested against real journals |
| Bindings XML parsing | Done | `edap/bindings.py`, `edap/binding_lookup.py` |
| Action dispatch | Done | `edap/actions.py`, `edap/ship_controls.py` — 0.1s dwell floor, 0.2s continuous default |
| macOS input backend | Done | `edap/platform/input/macos.py` — Quartz CGEvent, modifier combos work |
| Screen capture (one-shot) | Done | `edap/platform/screen/macos.py`, `edap/capture.py` — normalized regions |
| Config loading | Done | `edap/config.py`, `config.example.toml` |
| Runtime context assembly | Done | `edap/runtime.py` — config fallback, path resolution, optional binding lookup, platform adapter wiring |
| CV pipeline (compass, navpoint, destination) | Not ported | No template matching in `edap/` yet — blocked on plan 0002 |
| Align loop | Not ported | Depends on CV pipeline |
| Journal watcher | Done | `edap/state.py` — incremental tailing with rollover support and tests |
| Auto-zero throttle on arrival | Done | `edap/routines.py` — dispatches `SetSpeedZero` on `SupercruiseExit` |
| Jump sequencing | Done | `edap/routines.py` — retrying journal-driven routine with start/completion timeouts and throttle-zero follow-up |
| Refuel sequencing | Deferred | Legacy behavior is understood, but implementation is intentionally paused for now |
| Dock sequencing | Done | `edap/routines.py` — waits on journal events, boosts after SCX and settles, drives legacy-style docking request UI walk (with `ui_left` to exit contacts menu), retries after DockingDenied with configurable delay, optionally chains station refuel menu |
| Undock sequencing | Done | `edap/routines.py` — menu walk (UI_Back x10, HeadLookReset, UI_Down, UI_Select), polls for `Undocked` event; live-validated |
| Station / docked state detection | Partial | `edap/state.py` derives coarse statuses like `in_station`, `starting_docking`, and `in_docking`, but there is no dedicated docked/station snapshot model yet |
| Hotkey registration | Parked | `keyboard` lib doesn't work on macOS; likely future direction is a menu-bar app |
| Legacy autopilot loop migration | Not ported | `dev_autopilot.py` remains the behavior reference; new `edap/` routines are still minimal |

## Unverified on macOS / CrossOver

- **CV templates on Retina + CrossOver.** `scratch_cv.py` has been run against a live CrossOver session. Navpoint passed (0.59 vs 0.5 threshold). Compass near-missed (0.29 vs 0.3 threshold) — template needs re-baking from a frame captured on this machine. Destination was 0.0 as expected (ship was not in supercruise with a target locked). Compass re-bake is the next CV task.
- **Real-time capture loop.** Only ever captured a single frame. Frame rate and capture cost in a continuous loop are unmeasured.
- **Journal write latency vs poll rate.** We have not measured how quickly Elite (through CrossOver) flushes events to disk relative to a 0.5s poll.
- **Window focus during autopilot.** `CGEventPost` is global on macOS; behavior across focus loss and multi-monitor setups during a live run is untested.

Full detail: `docs/research/0004-legacy-autopilot-port-status.md`.

## Next Plans

| Plan | File | Depends on | Ready to start |
| --- | --- | --- | --- |
| 0002 CV Pipeline Scaffold | `docs/plans/0002-cv-pipeline-scaffold.md` | nothing | yes |
| 0003 Journal-Driven Routines | `docs/plans/0003-journal-driven-routines.md` | nothing | yes |
| 0004 Runtime Diagnostics Dashboard | `docs/plans/0004-runtime-diagnostics-dashboard.md` | 0002/0003 helpful first | after |

Plans 0002 and 0003 are independent and can run in parallel.

## Ideas / Future Work

These are not scheduled yet but worth capturing for planning.

- **Galaxy map input.** Drive the in-game galaxy map to type a destination system name procedurally, replacing manual system selection. Would unlock fully automated route setting.
- **Market trading.** Read commodity data from journal/market logs, then drive buy/sell menus via procedural input sequences to automate trade runs.
- **Human-like input variation.** Add randomized dwell and inter-key delay variation to all synthetic input so sequences look less robotic. For menu-heavy flows (market buy/sell), include occasional overshoot-and-correct behavior (navigate past item, back up) to mimic human selection patterns.
- **Monitoring and command center CLI.** A multi-panel terminal UI showing: ship and commander status (location, credits, cargo) in one panel, and a concise running log in another (docked at X, refueled, bought N units of Y, etc.). Likely built on `rich` or `textual`.

- Next task in 0003: `undock` is live-validated. `refuel` is the only remaining routine; it remains intentionally deferred.
- `refuel` is intentionally deferred for now.
- Next task in 0002: re-bake `templates/compass.png` from a live capture. Run `uv run python3 scratch_cv.py --config config.toml --save-raw /tmp/cv-raw.png`, then crop the compass from the raw frame.
- Destination template needs a supercruise test before deciding whether it also needs re-baking.
- Then: use plan 0004 to measure capture-loop performance and journal latency.
