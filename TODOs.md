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
- Current observed issue: `ship_controls.py` resolves bindings and emits expected terminal progress/JSON, but the game did not react to repeated `SetSpeedZero` or `RollLeftButton` taps when focused through CrossOver.
- New evidence: the same synthetic key path does reach Elite chat, so macOS -> CrossOver -> game delivery works at least for text input.
- Current theory: flight controls may need true key-down, short dwell, and key-up timing rather than the current tap-style `keystroke` behavior in `edap/platform/input/macos.py`.
- Follow-up implementation target: add real press/release semantics in the macOS input backend and re-test `SetSpeedZero` plus one flight-axis action.
