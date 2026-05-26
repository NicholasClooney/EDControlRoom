# TODOs

## Parked

### Previous Python environment cleanup

- Figure out which Python environment previously held the working project dependencies before `mise` became the active `python3`.
- Identify where those packages were installed.
- Decide whether that older environment should be removed or kept as a reference.
- If removing it, document the cleanup steps before deletion.

### OpenCV and Python version compatibility

- Current `mise` / `uv` setup is on Python `3.12`.
- The pinned `opencv-python~=4.2.0.34` does not resolve on Python `3.12`.
- Decide later whether to:
  - move to a newer OpenCV version compatible with `3.12`, or
  - use an older Python version for legacy dependency compatibility.

## Active

### Manual control path

- Use `ship_controls.py` as the current live manual control entry point instead of `diagnostics.py`.
- Extend it as needed for direct action testing beyond `SetSpeedZero`.
- Confirmed on the current setup: flight controls respond when the macOS backend sends real key-down, short dwell, and key-up events.
- Use this path as the baseline for further ship-control testing instead of the older tap-style `keystroke` behavior.
- Plain unmodified ship-control keys are the current known-good path.
- `System Events` modifier-combo ship controls such as `Ctrl+...` are still unresolved on the current setup.
- A later experiment that switched letters to macOS key codes regressed previously working plain-key control delivery; that change was reverted.
- Measured so far on the current setup:
  - `SetSpeedZero` works with `hold_s = 0.0`
  - `RollLeftButton` did not work reliably at `0.0`, `0.01`, or `0.02`
  - `RollLeftButton` started working at `0.05`
  - `RollLeftButton` works at `0.1`
  - `RollLeftButton` feels smoother at `0.2`
- Implemented policy:
  - minimum dwell floor is now `0.1s` for all actions
  - continuous controls default to `0.2s`
  - explicit holds below `0.1s` are clamped up to `0.1s`
  - continuous controls can be dispatched by total requested actuation time via `ceil(total / dwell)`

### Manual harness

- Keep `ship_controls.py` as the human test surface for live in-game control testing.
- Add only the smallest features that materially improve manual verification loops.
- Avoid turning it into a second app, console, or long-term runtime surface.
- Current useful features:
  - action sequences
  - per-step `delay=`
  - global or per-step hold/total planning
- Good future candidates: `--interval-seconds`, `--dry-run`, and explicit `tap|press|release` mode selection.

### Control timing policy

- Treat controls as two categories until proven otherwise:
  - discrete actions, where a single activation is enough
  - continuous actions, where each activation needs a minimum dwell time
- Likely discrete examples:
  - `SetSpeedZero`
  - `SetSpeed100`
  - `HyperSuperCombination` / FSD-style actions
- Likely continuous examples:
  - `RollLeftButton`
  - `RollRightButton`
  - `PitchUpButton`
  - `PitchDownButton`
  - `YawLeftButton`
  - `YawRightButton`
- Implemented direction:
  - keep low-level backend primitives generic
  - apply dwell timing defaults for continuous controls in a higher-level policy layer
  - keep those defaults configurable in config
  - if a routine needs total actuation time `t`, dispatch `ceil(t / dwell)` activations using the configured dwell
- Manual testing guideline:
  - when generating test sequences with contradictory actions, leave time between them so the effect is observable
  - examples:
    - `SetSpeedZero -> SetSpeed100 -> SetSpeedZero`
    - `RollLeftButton -> RollRightButton -> RollLeftButton`
  - in practice, prefer explicit per-step `delay=` between those actions
