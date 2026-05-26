# 0002: Portability Open Questions

This note captures the current open research tracks that are useful, but not yet the best place to spend implementation time.

## Scope

These correspond to the three earlier items that were intentionally deferred in favor of concrete verification and extraction work:

1. binding normalization design
2. input semantics design
3. screen and capture calibration follow-up

## Recommended Home

Keep open-ended work like this in `docs/research/` while it is still exploratory.

Once a direction is chosen and we are ready to treat it as project contract, the settled version should move into either:

- `docs/design/` for architecture and interface decisions
- the active plan doc when the choice becomes part of the implementation sequence

That split keeps the plan focused on execution, while leaving the dead ends and unresolved tradeoffs in research notes where they belong.

## 1. Binding Normalization Design

Question:

How should Elite `.binds` tokens map into a platform-neutral input model that later fans out to macOS, and eventually Windows again?

Why this is still research:

- real `.binds` files vary by device mix and modifier usage
- some keys are straightforward keyboard keys, some are special keys, and some may be gamepad-only
- the current parser extracts raw-ish values like `J`, `LeftShift`, and `Space`, but the output contract for the input layer is not settled yet

What the implementation should eventually decide:

- canonical key names
- canonical modifier names
- treatment of unsupported bindings
- whether multiple bindings per action are preserved or reduced to a single effective binding

Recommended next trigger:

Do this when bindings discovery is stable and we are ready to drive the first real autopilot action through the new backend.

## 2. Input Semantics Design

Question:

What operations should the input backend guarantee beyond a simple tap?

Current evidence:

- manual testing on the current macOS + CrossOver setup shows that tap-style synthetic input reaches Elite UI and in-game chat
- the same path has not yet been shown to drive ship controls like `SetSpeedZero` or `RollLeftButton`
- the current likely gap is missing true key-down and key-up behavior with a short dwell
- this remains setup-specific evidence, not universal proof for every setup or later backend

What the implementation should eventually decide:

- tap semantics
- hold and release semantics
- modifier combo ordering
- retry or pacing behavior
- whether the diagnostic backend and the runtime backend should remain the same implementation

Remaining caution:

- treat true press/release semantics as an immediate implementation gap for the macOS backend
- re-check whether tap-only behavior is ever sufficient for ship controls after real press/release support exists

Recommended next trigger:

Do this before trusting further ship-control action ports, because the current backend now appears to prove UI delivery more than flight-control delivery.

## 3. Screen And Capture Calibration Model

Question:

How should vision regions and scaling be represented for Retina displays, CrossOver windows, and varying resolutions?

Why this is still research:

- the legacy CV code assumes a fixed 1080p-style layout
- a first-pass config seam now exists for normalized base capture geometry and named subregions
- the macOS diagnostic proved screen capture works, not that the old geometry assumptions are valid
- we still need real screenshots and template-match feedback before choosing a durable calibration model

What the implementation should eventually decide:

- whether coordinates are absolute or normalized
- whether scaling is global or per-region
- whether calibration is manual, auto-detected, or preset-driven
- how debug captures should be stored and compared

Recommended next trigger:

Do this right before porting the first real vision-dependent autopilot routine, not before.
