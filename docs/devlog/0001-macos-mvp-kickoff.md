# Devlog 0001: macOS MVP Kickoff

## Summary

This checkpoint moved the project from a Windows-only prototype mindset to a macOS-first portability track aimed at running Elite Dangerous through CrossOver.

The key result is that the platform assumptions were tested directly on the current machine instead of being left theoretical.

## What Was Added

- `AGENTS.md` to document repository direction and working rules
- a rewritten `README.md` describing the macOS-first roadmap and diagnostics workflow
- `config.example.toml` as the initial config shape
- the `edap` package for extracted config, state, bindings, diagnostics, and platform adapter code
- `diagnostics.py` as a thin CLI entry point for runtime checks
- the portability plan in `docs/plans/0001-macos-mvp-portability-plan.md`

## What Was Proven

The following are now proven on the current macOS + CrossOver setup:

- CrossOver journal path discovery works
- journal parsing works against a real Elite Dangerous journal
- screen capture works
- synthetic key delivery into the focused CrossOver Elite window works
- repeated tap-style input reaches the game UI on this machine

The last point was first confirmed with a direct `osascript` keystroke test, then validated through `diagnostics.py` using:

```sh
python3 diagnostics.py --send-test-key --test-key j --delay-seconds 5 --repeat 3
```

Observed result: `jjj` arrived in the focused Elite Dangerous window.

Later manual testing narrowed the conclusion:

- repeated taps also appear in Elite chat
- `ship_controls.py` action dispatch still did not move ship controls like `SetSpeedZero` or `RollLeftButton`
- the likely backend gap is that `edap/platform/input/macos.py` still uses tap-style `keystroke` behavior instead of true key-down, dwell, and key-up timing

## What Is Implemented

### Diagnostics foundation

- config loading from TOML
- config validation for types, supported platforms, and invalid path shapes
- journal parsing extracted from legacy code
- bindings parsing extracted from legacy code
- platform path adapters for macOS and Windows
- reusable diagnostics service layer
- lightweight unittest coverage for config, state, bindings, and path discovery

### macOS diagnostics

- CrossOver-aware journal path fallback discovery
- broader CrossOver bindings discovery covering both `Local Settings/Application Data` and `AppData/Local`
- screen capture diagnostic
- native macOS input backend using `osascript`
- delayed and repeated test key sending
- structured reporting for configured, auto-detected, and effective paths

## Known Gaps

- there is not yet a real `config.toml` in the repo root
- the legacy autopilot loop has not been ported onto the new interfaces
- the normalized binding lookup seam exists, but it is not yet wired into runtime actions
- the macOS runtime input backend likely needs true press/release semantics before ship-control actions can be trusted

## Recommended Next Step

The next agent should focus on:

1. config validation and local `config.toml` workflow
2. binding-driven runtime actions using the new lookup seam
3. a first small action port, with `SetSpeedZero` as the preferred candidate
4. porting later steering-heavy actions only after the early runtime path is stable
