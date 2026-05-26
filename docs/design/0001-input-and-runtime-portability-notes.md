# 0001: Input and Runtime Portability Notes

## Status

Draft

## Purpose

This document captures the design work that is adjacent to the macOS portability effort but not yet ready to be treated as a concrete implementation plan.

These notes exist to reduce drift while the project moves from diagnostics into actual runtime wiring.

## 1. Binding Normalization

### Problem

Elite Dangerous bindings come from `.binds` XML and use Elite-specific token names such as:

- `Key_J`
- `Key_Space`
- `Key_LeftShift`
- `Mouse_*` values that may not be portable to the current keyboard-first macOS path

The new runtime needs a normalized internal representation that is independent of:

- Elite XML naming
- platform-specific key naming
- the specific input backend implementation

### Goal

Introduce an internal key representation that can be consumed by:

- macOS keyboard injection
- future Windows input backends
- future Linux input backends
- possibly a future controller backend

### Proposed direction

The normalization layer should output canonical tokens such as:

- `j`
- `space`
- `shift`
- `ctrl`
- `alt`
- `up`
- `down`
- `left`
- `right`

Bindings should remain expressed as semantic game actions first, for example:

- `SetSpeedZero`
- `PitchUpButton`
- `HyperSuperCombination`

That means the runtime should ask for an action binding, not a raw key.

### Immediate next step

Build a lookup layer that resolves:

- game action name
- normalized key
- normalized modifier, if present

This should happen before broader autopilot action extraction.

## 2. Input Semantics Contract

### Problem

The current macOS backend is sufficient for diagnostics and visible key taps, but autopilot needs clearer semantics than “send a key.”

The runtime will need to distinguish between:

- tap
- hold
- release
- modifier combo
- repeated action

### Why this matters

Some actions are naturally tap-based:

- menu navigation
- scanner trigger
- FSD toggle

Some actions are naturally hold-based:

- pitch up
- pitch down
- yaw left/right
- roll left/right

The current `osascript` path is best proven for taps. It is not yet a strong guarantee for precise continuous-control semantics.

### Proposed direction

Define the contract at the interface level first, even if the first backend is limited.

Minimum operations:

- `tap(action)`
- `press(action)`
- `release(action)`
- `repeat(action, count)`

The backend should also make limitations explicit. If the macOS backend cannot reliably support true held-state behavior for certain actions, that should be visible at the interface or capability level instead of being hidden.

### Current evidence

Manual testing on the current macOS + CrossOver setup shows a narrower result:

- synthetic tap-style input reaches the game
- repeated taps appear in in-game chat
- ship controls respond once the backend sends real key-down, short dwell, and key-up events
- plain unmodified ship-control keys are the current known-good path
- modifier-combo ship controls such as `Ctrl+...` are not yet reliable through the current `System Events` backend

This matters most for:

- `PitchUpButton`
- `PitchDownButton`
- `YawLeftButton`
- `YawRightButton`
- `RollLeftButton`
- `RollRightButton`

The result should be treated as setup-specific evidence, not a universal guarantee. The current confirmed requirement on this machine is real press/release timing for ship-control delivery.

Measured findings on the current setup:

- `SetSpeedZero` works with `hold_s = 0.0`
- `RollLeftButton` did not work reliably at `0.0`, `0.01`, or `0.02`
- `RollLeftButton` started working at `0.05`
- `RollLeftButton` works at `0.1`
- `RollLeftButton` feels smoother at `0.2`
- a later experiment that switched letter keys to physical macOS key codes regressed previously working plain-key ship controls and was reverted

### Immediate next step

Document backend capabilities and keep the interface level explicit:

- simple tap
- repeated tap
- press followed by delayed release

The first runtime ports should use real key-down, short dwell, and key-up behavior in the macOS backend for flight controls.

### Control categories

The controls appear to split into two policy categories:

1. discrete actions
   A single activation is enough.
   Examples likely include:
   - `SetSpeedZero`
   - `SetSpeed100`
   - FSD / jump-style actions

2. continuous actions
   A single activation still needs a dwell time to register reliably.
   Examples likely include:
   - `RollLeftButton`
   - `RollRightButton`
   - `PitchUpButton`
   - `PitchDownButton`
   - `YawLeftButton`
   - `YawRightButton`

Implemented policy direction:

- keep the low-level macOS input backend generic
- keep `hold_s` available as the primitive
- add a higher-level dwell policy for control dispatch
- make those defaults configurable

Current implemented model:

- all actions have a minimum dwell floor of `0.1s`
- continuous controls default to `0.2s`
- explicit holds below `0.1s` are clamped to `0.1s`

For continuous controls, if a routine needs total actuation time `t`, the current model is:

- choose a default dwell duration `d` for each activation
- dispatch `ceil(t / d)` activations

This is now implemented as a policy layer on top of the current backend.

### Manual harness boundary

`ship_controls.py` should remain the human testing harness for live in-game verification.

That means:

- keep the CLI narrow and task-focused
- add only small features that materially improve manual testing
- avoid growing it into a second app or a long-term runtime shell

Reasonable next additions if needed:

- configurable interval between repeats
- dry-run binding resolution
- explicit `tap`, `press`, and `release` modes

Current useful sequence semantics:

- semicolon-separated action sequences
- per-step `repeat=`, `hold=`, `total=`, and `delay=`

Manual testing guideline:

- contradictory actions should not be scheduled back-to-back without a gap if the goal is to observe their effect
- examples:
  - `SetSpeedZero -> SetSpeed100 -> SetSpeedZero`
  - `RollLeftButton -> RollRightButton -> RollLeftButton`
- prefer explicit per-step `delay=` when building those test sequences

## 3. Screen and Capture Calibration Model

### Problem

The legacy CV code assumes:

- 1080p-like layout
- fixed screen fractions
- default orange HUD
- a visible game window occupying predictable geometry

That will be fragile on macOS because of:

- Retina scaling
- CrossOver window sizing
- different desktop display layouts

### Goal

Make capture coordinates and template regions configurable without immediately rewriting the CV pipeline.

Current practical seam:

- `screen.resolution_width`, `screen.resolution_height`, and `screen.scale` remain the concrete reference dimensions
- `screen.capture.left/top/right/bottom` defines the base normalized capture box
- `screen.capture.regions.*` defines named normalized subregions such as `center` and `compass`
- diagnostics reports the effective pixel layout for those regions

### Proposed direction

Prefer normalized geometry as the main representation:

- fractions relative to capture width/height

Allow explicit overrides where needed:

- configured resolution
- configured scale
- saved calibration presets later if required

This keeps the first port simple while allowing refinement later.

### Immediate next step

Collect a small set of real macOS/CrossOver screenshots and compare:

- full-screen capture size
- effective UI placement
- whether the current normalized regions still roughly align

Do not redesign the CV pipeline until that evidence exists.

## Relationship to Runtime Work

The two concrete runtime options discussed earlier are complementary, not redundant.

### Option 1: Load resolved bindings and expose a lookup

This is the narrower data layer.

It answers:

- what actions are available
- what key/modifier each action resolves to
- what is missing or unsupported

This is the right first step because it creates a stable bridge from Elite configuration into the new runtime.

### Option 2: Resolve journal, bindings, and platform adapters into one runtime context

This is the broader runtime wiring layer.

It answers:

- what config is active
- what paths were resolved
- what bindings are active
- what platform backends are active
- what services the autopilot can call

### Recommended sequence

Do option 1 first, then option 2.

Reason:

- option 1 gives the runtime a stable action-to-input mapping
- option 2 becomes much cleaner once that mapping already exists

So these are not alternative choices. They are adjacent layers in the same direction.

## Open Questions

- How reliable is `osascript` for held directional control in Elite through CrossOver beyond the current machine?
- Does any later runtime action reveal a material difference between held directional input and repeated taps on other setups?
- Should unsupported or mouse-only Elite bindings be surfaced as warnings or hard errors?
- How many CrossOver bottle layouts do we need to support before adding bottle-aware selection?
- Do we need a later calibration command for CV region tuning?

## Deferred Decisions

- Whether the long-term macOS input backend remains `osascript`-based
- Whether controller/virtual HID output should ever be part of the MVP
- Whether the runtime should be bottle-aware or rely on explicit config for multi-bottle setups
