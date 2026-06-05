# Manual Journal Routine Testing

This document describes the current supported live test flow for the first journal-driven routine:

- `JournalWatcher` tails the latest `Journal.*` file incrementally
- `auto_zero_throttle_on_arrival` dispatches `SetSpeedZero` when a `SupercruiseExit` event appears
- `run_routine.py` is the supported manual harness for running that path against a real Elite session

## Current Command

Run:

```sh
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival
```

Useful variants:

```sh
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival --delay-seconds 5
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival --poll-interval-seconds 0.5
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival --hold-seconds 0.1
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival --repeat 2
```

## What This Proves

This manual test is meant to prove the first complete journal-driven runtime path on macOS + CrossOver:

1. journal path resolution works in the shared runtime context
2. `JournalWatcher` can see new events arrive in the live journal
3. the routine reacts to `SupercruiseExit`
4. `ShipControls` dispatches `SetSpeedZero` through the bindings lookup and macOS input backend

This does not prove broader autopilot behavior. It only proves the watcher-to-controls path for one simple routine.

## Setup

Before running the manual test:

1. Ensure `config.toml` resolves both the journal directory and bindings file, either explicitly or through auto-detection.
2. Ensure macOS Accessibility / input permissions are already working for the repo's existing diagnostics and manual control scripts.
3. Ensure Elite Dangerous is running through CrossOver and can receive synthetic keyboard input on the current machine.

If you are unsure about the runtime prerequisites, verify them first with:

```sh
python3 diagnostics.py --config config.toml
python3 ship_controls.py --config config.toml --action SetSpeedZero --delay-seconds 3
```

## Manual Test Flow

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

## Useful Flags

- `--delay-seconds 5`
  Gives you time to focus the game window before the watcher starts.
- `--poll-interval-seconds 0.5`
  Controls journal polling cadence.
- `--hold-seconds 0.1`
  Forces a specific dwell on the dispatched action.
- `--repeat 2`
  Sends `SetSpeedZero` more than once if you want a more aggressive manual check.

## Failure Modes To Watch

- The command exits early because journal or bindings resolution fails.
- The routine keeps waiting forever because no `SupercruiseExit` event arrives in the watched journal.
- The JSON result shows the trigger event correctly, but the ship does not respond, which would point at an input-routing or in-game focus problem rather than a journal problem.
- The game reacts inconsistently, which may justify trying a larger dwell or repeat count before changing routine logic.

## Follow-On Work

Once this manual flow is confirmed in a real session, the next journal-driven routine to add is `jump`.
