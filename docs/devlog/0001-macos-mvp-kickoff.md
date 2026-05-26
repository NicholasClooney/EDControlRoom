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
- ship controls respond once the macOS backend uses true key-down and key-up events with a short dwell

The last point was first confirmed with a direct `osascript` keystroke test, then validated through `diagnostics.py` using:

```sh
python3 diagnostics.py --send-test-key --test-key j --delay-seconds 5 --repeat 3
```

Observed result: `jjj` arrived in the focused Elite Dangerous window.

Later manual testing narrowed the conclusion:

- repeated taps also appear in Elite chat
- `ship_controls.py` action dispatch did not move ship controls while `edap/platform/input/macos.py` still used tap-style `keystroke` behavior
- after switching the backend to real key-down, dwell, and key-up behavior, `SetSpeedZero` worked in-game
- later timing tests showed `SetSpeedZero` works with `hold_s = 0.0`, while `RollLeftButton` needed a non-zero dwell and became reliable starting around `0.05`, with smoother behavior around `0.2`
- the resulting control policy is now implemented with a `0.1s` minimum dwell floor for all actions and a `0.2s` default dwell for continuous controls
- later manual sequencing confirmed that contradictory actions should be separated with explicit delays when the goal is to observe each effect clearly
- later experiments showed that modifier-combo ship controls such as `Ctrl+...` are still unresolved through the current `System Events` backend
- an attempted letter-to-key-code macOS input change regressed previously working plain-key ship controls and was reverted to restore the last known-good sequence behavior

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
- a shared runtime assembly layer now exists, but it is still narrow and CLI-focused
- the binding lookup seam is now wired into a first small set of runtime actions plus one tiny composed routine
- broader ship-control coverage and pacing still need validation, but the macOS runtime input backend now has the required press/release foundation

## Recommended Next Step

The next agent should focus on:

1. validating dwell thresholds for more concrete ship-control actions
2. expanding the small runtime action surface where the bindings model already supports it
3. using the shared runtime context as the base for later autopilot-facing flows
4. porting later steering-heavy actions only after the early runtime path is stable
