# EDAutopilot

Elite Dangerous autopilot experimentation using computer vision, journal parsing, and synthetic keyboard input.

## Project Direction

This repository started as a Windows-focused prototype. The current direction is different:

- primary target: macOS
- game runtime: Elite Dangerous through CrossOver
- design constraint: keep future Windows compatibility in mind
- immediate goal: prove the platform/runtime plumbing before expanding autopilot behavior

That means the project is still in a portability-first phase rather than a feature rewrite.

## Current Status

See [docs/STATUS.md](docs/STATUS.md) for port status, what is stubbed, what is unverified, and which plan to pick up next.
See [docs/manual-journal-routine-testing.md](docs/manual-journal-routine-testing.md) for the current live manual test flow for the first journal-driven routine.

Active plans:

- [docs/plans/0002-cv-pipeline-scaffold.md](docs/plans/0002-cv-pipeline-scaffold.md) — probe whether legacy CV templates match on macOS + CrossOver.
- [docs/plans/0003-journal-driven-routines.md](docs/plans/0003-journal-driven-routines.md) — `JournalWatcher`, `jump`, `refuel`, `dock`, `undock`, `auto_zero_throttle_on_arrival`, plus a `run_routine.py` CLI.
- [docs/plans/0004-runtime-diagnostics-dashboard.md](docs/plans/0004-runtime-diagnostics-dashboard.md) — capture benchmark, journal-latency probe, and a `rich.live` stats-for-nerds dashboard.

## What `diagnostics.py` Is

`diagnostics.py` is the diagnostic runner entry point.

It is a small command or mode that validates core prerequisites without attempting to fly the ship. For this project, that means checking config, journal parsing, bindings parsing, screen capture, and test input delivery.

## Legacy Code

The original Windows-oriented implementation is still present as a behavior reference:

- `autopilot.py` — legacy app entry point
- `dev_tray.py` — tray and hotkey behavior
- `dev_autopilot.py` — most of the original logic
- `src/directinput.py` — Windows-specific input code

Do not treat these as the target structure for the macOS-first version.

## Diagnostics Usage

Copy `config.example.toml` to `config.toml` and fill in the journal and bindings locations if auto-detection is not sufficient. Leaving either path blank tells diagnostics to try platform auto-detection.

For capture settings, the current config supports:

- concrete reference dimensions via `screen.resolution_width`, `screen.resolution_height`, and `screen.scale`
- a base capture box via `screen.capture.left/top/right/bottom`
- named normalized subregions via `screen.capture.regions.*`

The normalized capture boxes are the forward-looking seam for later CV work. The reference dimensions are still the concrete values used by diagnostics today.

Then run:

```sh
python3 diagnostics.py --config config.toml
```

Optional checks:

```sh
python3 diagnostics.py --config config.toml --capture-screen
python3 diagnostics.py --config config.toml --send-test-key --test-key j
python3 diagnostics.py --config config.toml --send-test-key --test-key j --delay-seconds 5 --repeat 3
```

Current behavior:

- journal and bindings diagnostics are implemented
- macOS path fallback discovery is implemented
- diagnostics output distinguishes configured, auto-detected, and effective paths
- diagnostics output includes the effective capture layout in normalized and pixel terms
- screen capture diagnostic can save a debug image
- macOS test input is wired through a native Quartz `CGEvent` backend (via `pyobjc-framework-Quartz`)

On macOS, synthetic input and screen capture may require Accessibility or Screen Recording permissions depending on system settings.

## Manual Utility Scripts

Beyond `diagnostics.py`, five scripts are useful for watching journal traffic, poking at bindings, exercising single controls, and running the current journal-driven routines. All honor the same `--config` flag and reuse the shared runtime context where applicable.

### `check_bindings.py`

Verifies which Elite actions resolve to a usable binding for the current bindings file.

```sh
python3 check_bindings.py
python3 check_bindings.py --verbose
python3 check_bindings.py --json
```

The plain output reports required-binding coverage. `--verbose` adds optional bindings. `--json` emits a full structured payload that includes `all_supported` and `all_issues`, which is the easiest way to discover what key and modifier are bound to a given action.

To inspect specific actions, pipe the JSON into `jq` or a small Python snippet:

```sh
python3 check_bindings.py --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['all_supported'].get('YawLeftButton'))"
```

### `watch_journal.py`

Watches the live Elite journal through `JournalWatcher`, prints only a small filtered event set to stdout, and logs every raw event to `artifacts/journal-watcher.log`.

```sh
python3 watch_journal.py
```

This is the quickest way to confirm that the repo is seeing real-time journal transitions like `StartJump`, `SupercruiseEntry`, `SupercruiseExit`, and `FSDJump` on the current machine before testing a higher-level routine.

### `ship_controls.py`

Sends one or more ship-control actions through the binding lookup and the macOS input backend. Useful for confirming that a key actually reaches the in-game cockpit.

```sh
python3 ship_controls.py --action SetSpeedZero --delay-seconds 3
python3 ship_controls.py --delay-seconds 3 --sequence "SetSpeedZero; RollLeftButton total=0.45; SetSpeed100 delay=5"
```

Per-step fields inside `--sequence` are `repeat=<n> hold=<seconds> total=<seconds> delay=<seconds>`. `total=` is only valid for continuous controls (roll, yaw, pitch) and plans the number of repeated activations from the requested total actuation time. `delay=` pauses before the step so the game window can stay focused between effects.

Plain bindings and modifier-combo bindings (`Ctrl+...` etc.) both work through the Quartz `CGEvent` backend. The earlier osascript-only quirks around `.` (`Key_Period`) and modifier combos are resolved.

### `set_binding.py`

Programmatically edits the `.binds` XML file, intended for agent-driven binding changes rather than navigating the in-game menu. Writes a `.bak` alongside the bindings file by default.

```sh
python3 set_binding.py PitchDownButton --show
python3 set_binding.py PitchDownButton --key i
python3 set_binding.py SetSpeedZero --key x --modifier ctrl
python3 set_binding.py PitchDownButton --slot secondary --key q
python3 set_binding.py PitchDownButton --clear
```

`--show` is read-only. `--key` accepts internal canonical names: letters (`a`-`z`), digits, punctuation literals (`. , [ ] / \ ; ' - =`), specials (`space`, `enter`, `tab`, `escape`, `backspace`, `delete`, `home`, `end`, `page_up`, `page_down`, arrows), modifier-as-key names (`left_shift`, `right_control`, ...), `numpad_<0-9>`, and `f<1-20>`. `--modifier` accepts the same modifier names plus the aliases `shift`, `ctrl`, `alt`. `--slot` is `primary` (default) or `secondary`. `--clear` empties the slot.

Changes take effect when Elite Dangerous next reads the bindings file. The game generally re-reads on launch and when entering the Controls menu, so close and reopen ED after a write to be safe.

### `run_routine.py`

Runs the current journal-driven routines against a live Elite session. The supported routines are:

- `auto_zero_throttle_on_arrival` — watches the journal for `SupercruiseExit` and dispatches `SetSpeedZero`
- `jump` — dispatches `HyperSuperCombination`, waits for jump start, waits to return to `in_supercruise`, then zeroes throttle
- `dock` — optionally waits for `SupercruiseExit`, sends the docking-request menu walk, waits for docking events, and can chain the in-station refuel menu
- `station_refuel_menu` — waits for `Docked`, then sends the station refuel menu sequence

```sh
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival
python3 run_routine.py --config config.toml --routine auto_zero_throttle_on_arrival --delay-seconds 5
python3 run_routine.py --config config.toml --routine jump --delay-seconds 5
python3 run_routine.py --config config.toml --routine jump --delay-seconds 5 --log-events
python3 run_routine.py --config config.toml --routine dock --delay-seconds 5 --log-events
python3 run_routine.py --config config.toml --routine dock --skip-supercruise-exit --delay-seconds 5 --log-events
python3 run_routine.py --config config.toml --routine dock --delay-seconds 5 --auto-refuel --log-events
```

The detailed manual test flow lives in [docs/manual-journal-routine-testing.md](docs/manual-journal-routine-testing.md).

## Existing Runtime Assumptions

The legacy computer vision code was built around:

- 1080p-style capture assumptions
- default orange Elite UI colors
- a visible game window

Those assumptions may need adjustment on macOS because of Retina scaling and CrossOver window behavior, but the vision logic itself is not the first thing to rewrite.

## Development

This project is still experimental. Do not leave it running unattended.

Run the lightweight verification harness with:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

For commits, use Conventional Commits.

Examples:

- `feat: add config loader`
- `refactor: split platform adapters from autopilot logic`
- `docs: update macos roadmap`
- `fix: validate missing journal path`
