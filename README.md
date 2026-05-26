# EDAutopilot

Elite Dangerous autopilot experimentation using computer vision, journal parsing, and synthetic keyboard input.

## Project Direction

This repository started as a Windows-focused prototype. The current direction is different:

- primary target: macOS
- game runtime: Elite Dangerous through CrossOver
- design constraint: keep future Windows compatibility in mind
- immediate goal: prove the platform/runtime plumbing before expanding autopilot behavior

That means the project is still in a portability-first phase rather than a feature rewrite.

## Current Plan

The active plan is documented in [docs/plans/0001-macos-mvp-portability-plan.md](docs/plans/0001-macos-mvp-portability-plan.md).

Short-term parked issues are tracked in [TODOs.md](TODOs.md).

In short, the current checkpoint has already proven:

- journal access from configured or auto-detected paths
- bindings access from configured or auto-detected paths
- screen capture from the visible game on macOS
- synthetic keyboard input into the CrossOver Elite Dangerous window

The current implementation focus is the seam between parsed Elite bindings and future runtime actions, using a shared runtime context plus small action ports onto the new platform interfaces.

On the current macOS + CrossOver setup, manual testing now shows a narrower result:

- synthetic key input reaches the game
- repeated taps appear in in-game chat
- flight controls respond once the macOS backend sends real key-down and key-up events with a short dwell
- plain unmodified ship-control keys are the current known-good path
- modifier-combo ship controls such as `Ctrl+...` are not yet reliable through the current `System Events` backend

Confirmed finding: CrossOver/Elite flight controls need real key presses, not just tap-style `keystroke` delivery.

Current control-timing policy:

- all actions have a minimum dwell floor of `0.1s`
- continuous controls default to `0.2s`
- continuous controls can also be driven by total requested actuation time

## What `diagnostics.py` Is

`diagnostics.py` is the diagnostic runner entry point.

It is a small command or mode that validates core prerequisites without attempting to fly the ship. For this project, that means checking config, journal parsing, bindings parsing, screen capture, and test input delivery.

## Current State

The existing codebase still contains the original Windows-oriented implementation:

- `autopilot.py` starts the legacy app flow
- `dev_tray.py` contains tray and hotkey behavior
- `dev_autopilot.py` contains most of the current logic
- `src/directinput.py` is Windows-specific input code

That code is useful as a behavior reference, but it should not be treated as the final structure for the macOS-first version.

## Near-Term Goals

- introduce explicit config for paths and hotkeys
- extract journal and bindings parsing into reusable modules
- isolate platform-specific input, paths, hotkeys, and screen capture
- build the macOS diagnostic runner
- reconnect autopilot logic only after diagnostics are stable

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
- macOS test input is wired through a native `osascript` backend for validation

On macOS, synthetic input and screen capture may require Accessibility or Screen Recording permissions depending on system settings.

## Configuration Direction

The project is moving away from hardcoded assumptions such as:

- Windows journal locations
- Windows bindings locations
- fixed start/stop shortcuts

Planned configurable items include:

- journal directory
- bindings file
- start hotkey
- stop hotkey
- scanner mode
- screen/capture scaling values
- base capture geometry
- named normalized subregions for future CV hooks

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
