# Elite Bindings Reference

This repo reads Elite Dangerous `.binds` XML directly. Future edits must use the
action and key names that Frontier writes into the file, not guessed names.

## Action Names

These are Elite XML action tags that matter to the current runtime:

- `SetSpeedZero`: throttle to 0%
- `SetSpeed100`: throttle to 100%
- `HyperSuperCombination`: jump / supercruise engage
- `UseBoostJuice`: boost
- `FocusLeftPanel`: open left ship panel
- `UI_Up`, `UI_Down`, `UI_Left`, `UI_Right`, `UI_Select`, `UI_Back`: menu navigation
- `CycleNextPanel`, `CyclePreviousPanel`: panel tab cycling
- `HeadLookReset`: reset headlook / center view
- `GalaxyMapOpen`: open galaxy map
- `CamZoomIn`: galaxy map route-plot hold action used by the Odyssey flow

## Important Gotcha

Boost is written as `UseBoostJuice` in the live `.binds` files on this macOS +
CrossOver setup. It is not written as `BoostButton`.

If a future routine needs boost, request `UseBoostJuice` in action lists and
binding lookups.

## Key Token Examples

Elite key tokens are not the same strings we send to the macOS input backend.
Examples from `.binds`:

- `Key_Tab`
- `Key_X`
- `Key_W`
- `Key_A`
- `Key_LeftBracket`
- `Key_RightBracket`
- `Key_LeftShift`
- `Key_Space`

The repo normalizes those XML tokens into backend-neutral names before dispatch:

- `Key_Tab` -> `tab`
- `Key_X` -> `x`
- `Key_W` -> `w`
- `Key_LeftShift` -> `left_shift`
- `Space` or `Key_Space` -> `space`

The normalization logic lives in [edap/bindings.py](/Users/nicholasclooney/Source/Projects/EDAutoPilotMKII/edap/bindings.py:62) and [edap/binding_lookup.py](/Users/nicholasclooney/Source/Projects/EDAutoPilotMKII/edap/binding_lookup.py:107).

## Discovery Note

On macOS, binding discovery currently scans CrossOver bottle paths and picks the
newest `.binds` file by mtime. If discovery becomes ambiguous across bottles,
set `paths.bindings_file` explicitly in `config.toml`.
