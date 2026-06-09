# 0003: Journal-Driven Routines

## Status

Planned, not started.

## Why

Two workstreams emerged from the legacy autopilot port-status review (`docs/research/0004-legacy-autopilot-port-status.md`):

1. Computer-vision-dependent routines (align, dock, undock menu walks) — gated on plan 0002.
2. Journal-only routines (jump, refuel, auto-zero-throttle on arrival) — buildable today on top of `edap/state.py`, `edap/ship_controls.py`, and `edap/actions.py`.

The journal-only workstream is the fastest way to exercise the full runtime end-to-end on macOS + CrossOver. It also gives us real numbers on journal write latency vs. our poll cadence, which feeds plan 0004.

## Scope

Three pieces, in roughly this order:

### 1. `JournalWatcher` in `edap/state.py`

A small class that tails the latest journal file and yields parsed events. Stateless beyond a file offset.

- Inputs: journal directory, optional initial offset (default: end of file, so a fresh watcher only sees new events).
- Output: an iterator or callback surface that emits one parsed JSON dict per new line.
- Rollover handling: when `get_latest_journal_log()` returns a path different from the one currently being tailed, switch to the new file and reset the offset to 0.
- Polling cadence: a single `poll_interval_s` knob, default `0.5s`. The watcher should not spin; it should sleep between polls.
- Testability: accept an injected clock / sleeper so tests can drive it deterministically. Mirror the pattern already in `edap/platform/input/macos.py` and `edap/routines.py`.

Reference: legacy `archive/legacy-windows/dev_autopilot.py:151-248` (`ship()`) reads the whole file each time. The new watcher should be incremental.

### 2. Routine extensions in `edap/routines.py`

Add one routine at a time, each modelled on its legacy counterpart but driven by the new `JournalWatcher` and `ShipControls`. Order of work:

1. `auto_zero_throttle_on_arrival(controls, watcher)` — listens for `SupercruiseExit`, dispatches `SetSpeedZero`. This is the smallest, lowest-risk routine and proves the watcher → controls path end-to-end.
2. `jump(controls, watcher)` — mirror `archive/legacy-windows/dev_autopilot.py:1128-1154`. Dispatch `HyperSuperCombination` with a held tap, wait for `starting_hyperspace` → `in_supercruise`, retry up to 3 times. No align fallback yet (that needs CV).
3. `refuel(controls, watcher, threshold_percent=33)` — mirror `archive/legacy-windows/dev_autopilot.py:1169-1196`. Trigger when fuel% < threshold AND star class in `{F, O, G, K, B, A, M}`. Dispatch the `SetSpeed100` → `SetSpeedZero` x3 sequence, then poll the watcher until `FuelLevel == FuelCapacity` or a timeout fires.
4. `dock(controls, watcher)` — mirror `archive/legacy-windows/dev_autopilot.py:955-992`. Drive the UI menu walk: `UIFocus`, `UI_Left`, `UI_Up`, `UI_Select`, etc. Wait on the journal transition `starting_docking` → `in_docking` → `in_station`. Retry the menu walk on timeout.
5. `undock(controls, watcher)` — drive the undock menu walk. Wait on `in_undocking` → `in_space`. See discrepancy note below.

All routines should follow the existing `RoutineResult` shape (or extend it) so that a CLI can report what was done.

### 3. `run_routine.py` CLI

Small entry point, in the repo root alongside `ship_controls.py`:

- `--config <path>` (shared)
- `--routine <name>` where name is one of the five above
- Per-routine flags as needed (`--threshold-percent`, `--max-retries`, `--timeout-s`)
- Prints each `RoutineResult` and the watcher events that drove it, so a human can audit what happened

Out of scope:

- Looping multiple routines together (e.g. full jump-refuel-position cadence). One routine per invocation.
- Hotkey-triggered routines. Hotkeys are parked (see research note 0004).
- Anything that needs CV (align, position/scan).

## Reference Pointers

- Legacy:
  - `archive/legacy-windows/dev_autopilot.py:151-248` — `ship()`, the event vocabulary the watcher should match.
  - `archive/legacy-windows/dev_autopilot.py:916-940` — `undock`. **Discrepancy:** the legacy code sends `SetSpeedZero x2` between the launch confirm and the `in_space` wait (lines 929-930). The ship is still in the docking bay at that point so zeroing throttle has no meaningful effect. The new implementation omits this step. If testing reveals the game requires the throttle to be low before undocking completes, revisit.
  - `archive/legacy-windows/dev_autopilot.py:955-992` — `dock`.
  - `archive/legacy-windows/dev_autopilot.py:1128-1154` — `jump`.
  - `archive/legacy-windows/dev_autopilot.py:1169-1196` — `refuel`.
- New runtime:
  - `edap/state.py:33-110` — current `read_ship_state` reads the whole file; the watcher is the incremental cousin.
  - `edap/routines.py` — existing `set_speed_zero_then_wait` is the shape to follow.
  - `edap/ship_controls.py` — dispatcher entry points; add new convenience methods (`hyper_super_combination`, `ui_focus`, `ui_back`, `ui_up`, `ui_down`, `ui_left`, `ui_right`) as routines need them.
  - `check_bindings.py --json` — quick way to confirm an action resolves before a routine tries to dispatch it.
- Research framing: `docs/research/0004-legacy-autopilot-port-status.md` (Port Status table, journal latency caveat).

## Acceptance Criteria

- `python3 run_routine.py --routine auto_zero_throttle_on_arrival` zero-throttles the ship on the next `SupercruiseExit` while the user flies manually, and prints the event that triggered it.
- `JournalWatcher` has unit tests covering: incremental reads, rollover to a new `Journal.*` file mid-run, and idle polling without growing memory.
- Each routine has at least one unit test that drives it with a stubbed watcher and stubbed `ShipControls`, asserting the action dispatch sequence.
- No routine spins on a busy loop; all waits go through an injected sleeper.
- `run_routine.py` honours Ctrl+C cleanly (no orphaned held keys; release everything before exit).

## Open Questions To Resolve While Building

- What is the right journal poll interval on this machine? Plan 0004's journal-latency probe will give a measured floor; until then, default to `0.5s` and make it configurable.
- The `dock` / `undock` menu walks in the legacy code use hardcoded sleeps between key taps. Keep those for now and note them as candidates for replacement with status-driven waits once the routines are running.
- `auto_zero_throttle_on_arrival` is a great candidate for a small `--watch` mode that keeps running across multiple supercruise exits. Add it only if it falls out cheap; otherwise one-shot is fine.

## Notes For The Next Agent

- Build the watcher first and prove it with a tiny script that just prints events. Skip ahead to routines only once you can see events landing in real time during a live session.
- Resist the urge to add an orchestration layer ("autopilot()") that chains routines together. The legacy `autopilot()` is `archive/legacy-windows/dev_autopilot.py:1284-1305`; we will get there, but not in this plan.
- If a routine needs an action that isn't bound, fail loudly via `ActionDispatchResult`'s `status` / `reason` — do not silently no-op.
