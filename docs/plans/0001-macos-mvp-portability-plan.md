# 0001: macOS MVP Portability Plan

## Status

In Progress

## Context

The current project is designed around a Windows runtime:

- Keyboard input uses `ctypes.windll.user32.SendInput` in `src/directinput.py`.
- Journal and bindings discovery assume Windows paths under `%USERPROFILE%` and `%LOCALAPPDATA%`.
- Startup and control flow assume a tray app with hardcoded `Home` and `End` hotkeys.
- The autopilot logic, platform I/O, screen capture, and user configuration are all mixed together in `dev_autopilot.py`.

The immediate goal is not a full rewrite. The goal is a macOS-first MVP that runs Elite Dangerous through CrossOver, while preserving a structure that can support Windows again later.

We also need basic customization:

- Configurable journal path
- Configurable bindings path
- Configurable start/stop shortcuts
- Compatibility-minded module boundaries so we do not re-entangle platform-specific code

## Goals

- Make the codebase structurally ready for macOS and Windows support.
- Deliver a first milestone that proves the app can operate in a macOS + CrossOver setup.
- Introduce explicit configuration instead of hardcoded paths and shortcuts.
- Keep the existing OpenCV autopilot logic largely intact for now.

## Non-Goals

- Full rewrite of autopilot behavior
- UI redesign
- Full parity across macOS and Windows in the first pass
- Reworking the navigation/computer vision algorithms
- Autodetecting every CrossOver bottle layout up front

## Recommendation

The next implementation milestone should be a macOS diagnostic runner, not full autopilot.

This milestone should prove the four platform-sensitive capabilities that the existing project depends on:

1. Read the Elite Dangerous journal from a configured path
2. Read keybindings from a configured path
3. Capture the visible game area from macOS
4. Send synthetic keyboard input to the CrossOver Elite Dangerous window

Only after those work reliably should we wire the full autopilot loop back in.

## Proposed Architecture

Split the current monolith into platform-neutral logic plus platform-specific adapters.

### Core modules

- `edap/config.py`
  - Load config from file
  - Validate paths and runtime options
- `edap/state.py`
  - Journal parsing
  - Ship state extraction
- `edap/bindings.py`
  - Bindings XML parsing
  - Internal normalized key model
- `edap/vision.py`
  - Screen-region processing
  - Template matching
  - Offset calculation
- `edap/autopilot.py`
  - High-level routines: align, jump, refuel, position
  - No direct platform calls except through injected interfaces

### Platform adapter modules

- `edap/platform/input/base.py`
  - Shared input interface
- `edap/platform/input/macos.py`
  - macOS synthetic key events
- `edap/platform/input/windows.py`
  - Existing direct input logic migrated from `src/directinput.py`
- `edap/platform/paths/base.py`
  - Path resolution interface
- `edap/platform/paths/macos.py`
  - CrossOver-aware path helpers and config fallbacks
- `edap/platform/paths/windows.py`
  - Existing Windows path behavior
- `edap/platform/hotkeys/macos.py`
  - Start/stop hotkey registration
- `edap/platform/hotkeys/windows.py`
  - Existing behavior, cleaned up
- `edap/platform/screen/macos.py`
  - macOS screen capture
- `edap/platform/screen/windows.py`
  - Existing PIL/ImageGrab-based behavior if retained

### App entry points

- `main.py`
  - Load config
  - Resolve platform adapters
  - Start app mode
- `diagnostics.py`
  - Run the macOS diagnostic workflow
- `tray.py` or equivalent
  - Optional control surface after MVP

## Configuration

Add a user-editable config file. `config.toml` is recommended because it is readable and supports nested sections cleanly.

### Initial config surface

```toml
[paths]
journal_dir = "/path/to/journals"
bindings_file = "/path/to/Custom.binds"

[controls]
start_hotkey = "home"
stop_hotkey = "end"
scanner_mode = "off"

[screen]
resolution_width = 1920
resolution_height = 1080
scale = 1.0

[runtime]
platform = "macos"
debug = true
```

### Config behavior

- Manual configuration must work first.
- Auto-detection should be best-effort fallback, not a requirement.
- Missing or invalid config should produce actionable errors.
- The app should log the resolved paths and active platform backend on startup.

## Milestone 1: macOS Diagnostic Runner

Build a diagnostic command that validates the runtime assumptions before full autopilot is attempted.

### Scope

- Load config from disk
- Resolve journal path and bindings path
- Parse and print ship state
- Parse and print required bindings
- Capture one or more configured screen regions
- Attempt a harmless synthetic key press against the visible CrossOver window
- Register configurable start/stop hotkeys if feasible in the same runtime

### Suggested output

- Active platform backend
- Resolved journal path
- Resolved bindings path
- Latest journal file age
- Parsed ship status summary
- Missing keybinds, if any
- Screen capture dimensions and a simple saved debug image
- Input backend success/failure

### Acceptance criteria

- A user can configure journal and bindings locations without code changes.
- The diagnostic command succeeds on macOS when Elite Dangerous is visible through CrossOver.
- The diagnostic command can send at least one test key that reaches the game reliably enough to observe.
- Failures identify which subsystem broke: config, journal parse, bindings parse, screen capture, or input injection.

### Current checkpoint

Implemented:

- `config.example.toml`
- `edap/config.py`
- `edap/state.py`
- `edap/bindings.py`
- `edap/diagnostics.py`
- platform adapter bases and factories
- macOS/Windows path adapters
- macOS screen capture diagnostic
- macOS native input diagnostic through `osascript`
- `diagnostics.py` CLI with delay/repeat support for test keys
- config validation for types, supported platforms, and invalid existing path shapes
- structured diagnostics output for configured vs auto-detected vs effective journal/bindings paths
- broader CrossOver bindings discovery covering both `Local Settings\\Application Data` and `AppData\\Local`
- first-pass capture calibration config with normalized base/subregion geometry and effective pixel layout reporting

Proven on the current machine:

- CrossOver journal auto-detection works
- journal parsing works against a real log
- screen capture works
- synthetic key delivery into the focused CrossOver Elite window works

Still incomplete:

- the legacy autopilot loop has not been migrated onto the new interfaces
- bindings discovery still depends on a `.binds` file existing inside the active bottle layout
- repeated tap-style input is verified to reach the game UI and in-game chat on the current macOS + CrossOver setup
- ship-control input is now also proven once the macOS backend uses real key-down, dwell, and key-up behavior
- a higher-level control timing policy is now implemented with a `0.1s` minimum dwell floor and `0.2s` continuous-control default
- a shared runtime context now assembles config fallback, path resolution, input backend wiring, and optional action-scoped binding lookup
- the normalized binding lookup seam is now wired into a first small set of runtime actions plus one tiny composed routine
- the capture calibration seam exists, but the legacy CV pipeline has not been ported onto it yet
- the new verification harness exists, but broader runtime and integration coverage is still needed

Related open research notes:

- `docs/research/0001-macos-virtual-controller-output.md`
- `docs/research/0002-portability-open-questions.md`
- `docs/design/0001-input-and-runtime-portability-notes.md`

## Milestone 2: Reconnect Existing Autopilot Loop

Once the diagnostic runner is stable:

- Move current journal parsing into the new state module
- Move current bindings parsing into the new bindings module
- Move current OpenCV helpers into the new vision module
- Refactor `autopilot()` to depend on injected interfaces instead of globals
- Reuse existing templates and alignment heuristics

### Acceptance criteria

- Existing high-level loop can run without direct imports from Windows-only modules
- Start/stop controls come from config
- Input release and cleanup happen through the platform adapter

## Technical Risks

### 1. macOS synthetic input may not reach CrossOver reliably

This is the largest technical risk. The MVP should prove this before deeper refactoring.

Mitigation:

- Build a standalone input diagnostic first
- Keep the test action harmless and observable
- Log whether Accessibility / Input Monitoring permissions are missing

### 2. Retina scaling and window sizing may break current CV assumptions

The vision code assumes fixed screen fractions and a 1080p-like layout.

Mitigation:

- Make scale and capture regions configurable
- Save debug captures from the diagnostic runner
- Avoid rewriting the CV pipeline until actual macOS screenshots are inspected

### 3. CrossOver journal and bindings locations may vary

Bottle layout may differ across machines.

Mitigation:

- Make manual path config the primary path
- Add auto-detect only after at least one working known-good setup exists

### 4. Global state in current code complicates incremental migration

`dev_autopilot.py` mixes logging setup, config constants, globals, parsing, vision, and control flow.

Mitigation:

- Introduce new modules and move logic gradually
- Keep old files working until the diagnostic path is complete
- Avoid changing behavior and structure in the same step when possible

## Implementation Order

1. Add `docs/` plan and agree on MVP scope
2. Add config file loading and validation
3. Add a normalized internal key model
4. Extract journal and bindings parsing from `dev_autopilot.py`
5. Introduce platform interfaces for input, paths, and screen capture
6. Implement macOS diagnostic runner
7. Prove macOS input into CrossOver
8. Refactor autopilot loop to use injected adapters
9. Reintroduce tray/hotkey UX in a cleaner form

## Immediate Next Task

Finish the transition from diagnostics plumbing to autopilot portability:

- keep improving bottle-aware CrossOver path selection as needed
- add stronger local config workflow
- wire runtime actions through the normalized binding lookup seam
- port `SetSpeedZero` as the first small binding-driven runtime action
- treat hold-versus-tap as a follow-up capability question instead of a current gate

This is the next pickup point for the following agent.

## Follow-up Plans

The diagnostic and runtime-action milestones above are complete enough that follow-up work is now split into three smaller plans, each scoped tightly enough for one agent to pick up:

- `docs/plans/0002-cv-pipeline-scaffold.md` — answer whether the legacy CV templates match on macOS + CrossOver before any align/dock/undock loop is attempted.
- `docs/plans/0003-journal-driven-routines.md` — build `JournalWatcher` and the journal-only routines (jump, refuel, dock, undock, auto-zero-throttle-on-arrival) plus a `run_routine.py` CLI.
- `docs/plans/0004-runtime-diagnostics-dashboard.md` — capture-loop benchmark, journal-latency probe, and a `rich.live` stats-for-nerds dashboard.

Plans 0002 and 0003 are independent and can proceed in parallel. Plan 0004's first two deliverables feed defaults into plans 0002 and 0003, but are not strict blockers.
