# Project Status

_This is the maintained status document for the repo. Update it at the end of each session when project understanding, port status, or next steps change. Keep it current over time rather than treating it as a frozen checkpoint._

Last updated: 2026-06-05

## Where We Are

Plan 0001 (macOS MVP portability) is complete. The four hard platform problems are proven on the current macOS + CrossOver setup:

- Journal auto-detection and parsing works against a real log.
- Bindings XML parsing and action lookup works.
- Screen capture from the CrossOver window works.
- Synthetic key input via Quartz `CGEventPost` reaches the game, including modifier combos and punctuation keys that broke the earlier `osascript` backend.

A shared runtime context, config system, bindings lookup seam, and a small runtime action surface are wired up. Utility scripts `diagnostics.py`, `ship_controls.py`, `check_bindings.py`, `set_binding.py`, `view_bindings.py`, and `run_routine.py` all work.

The first journal-driven runtime pieces now exist:

- `JournalWatcher` tails the latest `Journal.*` file incrementally, starts at end-of-file by default, and rolls over to newer journal files.
- `auto_zero_throttle_on_arrival` exists as the first watcher-to-controls routine and dispatches `SetSpeedZero` on `SupercruiseExit`.
- `jump` now exists as the first retrying journal-driven routine. It dispatches `HyperSuperCombination`, waits for `StartJump` / hyperspace start, then waits to re-enter `in_supercruise` and zeroes throttle.
- `run_routine.py` now supports both `auto_zero_throttle_on_arrival` and `jump` as live manual harnesses for exercising journal-driven paths against a real Elite session.
- The current live manual test flows for those harnesses are documented in `docs/manual-journal-routine-testing.md`.

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
| Refuel sequencing | Stub | State reads exist; scoop sequence not wired |
| Dock sequencing | Stub | Needs UI menu walk plus status waits |
| Undock sequencing | Stub | Needs UI menu walk plus status waits |
| Hotkey registration | Parked | `keyboard` lib doesn't work on macOS; likely future direction is a menu-bar app |
| Legacy autopilot loop migration | Not ported | `dev_autopilot.py` remains the behavior reference; new `edap/` routines are still minimal |

## Unverified on macOS / CrossOver

- **CV templates on Retina + CrossOver.** Templates were authored against 1080p Windows captures. Nothing has run `cv2.matchTemplate` against a live CrossOver window on this machine yet.
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

- Next task in 0003: `refuel` — next journal-driven routine after watcher, arrival throttle, and jump.
- First task in 0002: `scratch_cv.py` — answers whether legacy templates match macOS + CrossOver captures before any align work is attempted.
- Then: use plan 0004 to measure capture-loop performance and journal latency once the first CV probe or first journal routine exists.
