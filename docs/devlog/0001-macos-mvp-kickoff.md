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

The last point was first confirmed with a direct `osascript` keystroke test, then validated through `diagnostics.py` using:

```sh
python3 diagnostics.py --send-test-key --test-key j --delay-seconds 5 --repeat 3
```

Observed result: `jjj` arrived in the focused Elite Dangerous window.

## What Is Implemented

### Diagnostics foundation

- config loading from TOML
- journal parsing extracted from legacy code
- bindings parsing extracted from legacy code
- platform path adapters for macOS and Windows
- reusable diagnostics service layer

### macOS diagnostics

- CrossOver-aware journal path fallback discovery
- screen capture diagnostic
- native macOS input backend using `osascript`
- delayed and repeated test key sending

## Known Gaps

- bindings auto-discovery is still incomplete on the current machine
- there is not yet a real `config.toml` in the repo root
- the legacy autopilot loop has not been ported onto the new interfaces
- there is not yet a normalized mapping from Elite binding tokens to the macOS input backend

## Recommended Next Step

The next agent should focus on:

1. config validation and local `config.toml` workflow
2. better CrossOver bindings discovery
3. normalized binding-to-input mapping
4. porting the first real autopilot actions onto the new interfaces
