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

Control-room startup warnings now print both the XML tag and a friendlier in-game label/menu hint for the routine-critical actions. Examples:

- `UseBoostJuice` -> `Engine Boost` in `Ship Controls > Flight Miscellaneous`
- `HyperSuperCombination` -> `Toggle Frame Shift Drive` in `Ship Controls > Flight Miscellaneous`
- `UIFocus` -> `UI Focus` in `Ship Controls > Mode Switches`
- `HeadLookReset` -> `Reset Headlook` in `Ship Controls > Headlook Mode`

These label/menu hints were compiled from community references, not Frontier-authored docs. Main sources used in the 2026-06-09 Control Room warning update:

- `EDAPGui` required-keybindings documentation on GitHub for the internal XML action names and the corresponding in-game control labels used by that autopilot project.
- `EDRefCard` for cross-checking how uploaded `.binds` files are categorized and described for players.
- `Ambient-Impact/Elite-Dangerous-bindings` on GitHub as an additional community-maintained binding reference.

Treat these as operator-facing hints, not canonical API contracts. When a label matters to workflow or support copy, verify it against the live Odyssey Controls menu.

## Important Gotcha

Boost is written as `UseBoostJuice` in the live `.binds` files on this macOS +
CrossOver setup. It is not written as `BoostButton`.

If a future routine needs boost, request `UseBoostJuice` in action lists and
binding lookups.

`read_bindings()` in [edap/bindings.py](/Users/nicholasclooney/Source/Projects/EDAutoPilotMKII/edap/bindings.py:79) currently resolves only one keyboard binding per action. If both `Primary` and `Secondary` are keyboard bindings, the `Secondary` entry overwrites the `Primary` entry in the runtime lookup.

Non-keyboard slots do not override a keyboard slot. Practical effect:

- keyboard `Primary` + joystick/mouse `Secondary` => runtime keeps the keyboard `Primary`
- joystick/mouse `Primary` + keyboard `Secondary` => runtime uses the keyboard `Secondary`
- joystick/mouse only, with no keyboard bind in either slot => runtime reports the action missing, because EDAP can only emulate keyboard input today

This is not just display detail. It changes what `control_room.py`, `run_routine.py`, and `ship_controls.py` will actually press.

Example:

- if `UI_Up` is `Primary = W` and `Secondary = UpArrow`, runtime dispatch resolves to `UpArrow`
- if `UI_Left` is `Primary = A` and `Secondary = LeftArrow`, runtime dispatch resolves to `LeftArrow`

This behavior matters in the galaxy map on the current Elite setup:

- `W/A/S/D` pans or moves the map view
- arrow-key `UI_*` bindings move the map/menu cursor/focus

So adding arrow-key secondaries to `UI_Up`, `UI_Down`, `UI_Left`, `UI_Right`
causes EDAP runtime navigation to use arrows instead of `W/A/S/D`, which is
currently what makes the galaxy-map menu/navigation flow work.

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
