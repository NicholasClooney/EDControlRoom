# Manual Journal Routine Testing

This document describes the current supported live test flows for the journal-driven routines that can be exercised manually today:

- `JournalWatcher` tails the latest `Journal.*` file incrementally
- `auto_zero_throttle_on_arrival` dispatches `SetSpeedZero` when a `SupercruiseExit` event appears
- `jump` dispatches `HyperSuperCombination`, waits for jump start, waits to re-enter `in_supercruise`, then dispatches `SetSpeedZero`
- `dock` can wait for `SupercruiseExit`, send the docking-request menu sequence, wait for docking events, and optionally trigger the station refuel menu after `Docked`
- `watch_journal.py` is the quickest low-level probe for confirming that live journal events are arriving as expected
- `run_routine.py` is the supported manual harness for running those paths against a real Elite session

## Current Commands

Run:

```sh
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival
python3 run_routine.py --config config.toml --routine jump
python3 run_routine.py --config config.toml --routine dock
```

Useful variants:

```sh
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival --delay-seconds 5
python3 run_routine.py --config config.toml --routine jump --delay-seconds 5
python3 run_routine.py --config config.toml --routine jump --max-retries 3 --start-timeout-seconds 20 --completion-timeout-seconds 30
python3 run_routine.py --config config.toml --routine dock --delay-seconds 5
python3 run_routine.py --config config.toml --routine dock --delay-seconds 5 --auto-refuel --log-events
python3 run_routine.py --config config.toml --routine dock --skip-supercruise-exit --delay-seconds 5
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival --poll-interval-seconds 0.5
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival --hold-seconds 0.1
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival --repeat 2
```

## What This Proves

These manual tests are meant to prove the first complete journal-driven runtime paths on macOS + CrossOver:

1. journal path resolution works in the shared runtime context
2. `JournalWatcher` can see new events arrive in the live journal
3. the routine reacts to `SupercruiseExit`
4. `ShipControls` dispatches `SetSpeedZero` through the bindings lookup and macOS input backend

This does not prove broader autopilot behavior. It only proves the watcher-to-controls path for a small journal-driven routine surface.

## Setup

Before running the manual test:

1. Ensure `config.toml` resolves both the journal directory and bindings file, either explicitly or through auto-detection.
2. Ensure macOS Accessibility / input permissions are already working for the repo's existing diagnostics and manual control scripts.
3. Ensure Elite Dangerous is running through CrossOver and can receive synthetic keyboard input on the current machine.

If you are unsure about the runtime prerequisites, verify them first with:

```sh
python3 watch_journal.py
python3 diagnostics.py --config config.toml
python3 ship_controls.py --config config.toml --action SetSpeedZero --delay-seconds 3
```

`watch_journal.py` prints only a small filtered event set to stdout and writes every raw event to `artifacts/journal-watcher.log`, which is useful when you want to confirm event sequences before testing a routine.

## Manual Test Flow: Arrival Throttle Zero

Recommended flow:

1. Start Elite Dangerous and get into a normal flight session.
2. Run:

```sh
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival --delay-seconds 5
```

3. During the countdown, focus the Elite window.
4. Enter supercruise.
5. Exit supercruise normally.
6. Observe whether throttle is immediately set to zero after the `SupercruiseExit` journal event lands.

## Manual Test Flow: Jump

Recommended flow:

1. Start Elite Dangerous and get into a normal flight session where a jump is valid.
2. Run:

```sh
python3 run_routine.py --config config.toml --routine jump --delay-seconds 5
```

3. During the countdown, focus the Elite window.
4. Make sure the ship is in a state where triggering `HyperSuperCombination` should begin a jump.
5. Observe whether the routine starts the jump, sees `StartJump` / hyperspace start in the journal, waits for return to `in_supercruise`, and then zeroes throttle.
6. If the routine times out, inspect the JSON result to see whether it failed before `StartJump` or after jump start but before `in_supercruise`.

## Manual Test Flow: Dock

Recommended flow:

1. Start Elite Dangerous and approach a station in supercruise.
2. Run:

```sh
python3 run_routine.py --config config.toml --routine dock --delay-seconds 5 --log-events
```

3. During the countdown, focus the Elite window.
4. Exit supercruise near the station.
5. Observe whether the routine:
   - sees `SupercruiseExit`
   - sends the docking-request menu walk
   - sees `DockingRequested` or `DockingGranted`
   - zeroes throttle
   - waits for `Docked`

For a manual trigger while already outside the station in local space, use:

```sh
python3 run_routine.py --config config.toml --routine dock --skip-supercruise-exit --delay-seconds 5 --log-events
```

To chain the in-station refuel menu automatically after docking:

```sh
python3 run_routine.py --config config.toml --routine dock --delay-seconds 5 --auto-refuel --log-events
```

## Expected Output

While waiting, stderr should show progress like:

```text
Starting auto_zero_throttle_on_arrival in 5s...
Watching /path/to/journal for SupercruiseExit events (poll 0.50s).
```

After the trigger, stdout should emit JSON that includes:

- resolved config path
- resolved journal directory and source
- resolved bindings file and source
- routine name
- dispatched action result
- the triggering journal event

The key part of the result is that `trigger_event.event` should be `SupercruiseExit` and the dispatch status should be `ok`.

For `jump`, the key part of the result is that:

- `routine` is `jump`
- `details.start_event.event` should be `StartJump`
- `trigger_event.event` should usually be `FSDJump` or `SupercruiseEntry`
- the final dispatch status should be `ok`

For `dock`, the key part of the result is that:

- `routine` is `dock`
- `details.request_event.event` should be `DockingRequested` or `DockingGranted`
- `trigger_event.event` should be `Docked`
- if `--auto-refuel` is used, `details.followup_action` should be `station_refuel_menu`

## Useful Flags

- `--delay-seconds 5`
  Gives you time to focus the game window before the watcher starts.
- `--poll-interval-seconds 0.5`
  Controls journal polling cadence.
- `--hold-seconds 0.1`
  Forces a specific dwell on the dispatched action.
- `--repeat 2`
  Sends `SetSpeedZero` more than once if you want a more aggressive manual check.
- `--max-retries 3`
  Controls retry budget for `jump`.
- `--start-timeout-seconds 20`
  Controls how long `jump` waits for hyperspace start.
- `--completion-timeout-seconds 30`
  Controls how long `jump` waits to return to `in_supercruise` after jump start.
- `--log-events`
  Logs every watched journal event during a routine run.
- `--event-log-path artifacts/run-routine-events.log`
  Controls where `run_routine.py --log-events` writes raw event output.
- `--skip-supercruise-exit`
  Starts `dock` immediately instead of waiting for `SupercruiseExit`.
- `--auto-refuel`
  After `Docked`, sends the station refuel menu sequence automatically.
- `--request-timeout-seconds 20`
  Controls how long `dock` waits for `DockingRequested` / `DockingGranted` after sending the menu sequence.

## Failure Modes To Watch

- The command exits early because journal or bindings resolution fails.
- The routine keeps waiting forever because no `SupercruiseExit` event arrives in the watched journal.
- The JSON result shows the trigger event correctly, but the ship does not respond, which would point at an input-routing or in-game focus problem rather than a journal problem.
- The game reacts inconsistently, which may justify trying a larger dwell or repeat count before changing routine logic.
- `jump` times out before `StartJump`, which points at a bad bind, bad focus, or a game state that was not actually ready to jump.
- `jump` sees `StartJump` but never reaches `FSDJump` / `SupercruiseEntry` before timeout, which points at an incomplete or interrupted jump sequence rather than a journal-resolution failure.
- If a routine behaves unexpectedly, compare the concise terminal output with the raw event log from `watch_journal.py` or `run_routine.py --log-events`.

## Follow-On Work

Once these manual flows are confirmed in a real session, the next journal-driven routine to add is `refuel`.
