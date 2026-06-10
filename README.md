# EDControlRoom

Multiplatform Elite Dangerous command-and-routine tooling focused on a shared runtime across macOS, Windows, and Linux. The active runtime is live-validated on macOS with Elite running through CrossOver by myself, @NicholasClooney, and the Windows path is now also live-validated by community member CMDR VRYAE. Linux remains unvalidated.

The current operator surface is [`control_room.py`](control_room.py). The project is not a hands-off flight bot; it is a live runtime and routine stack built around journal parsing, bindings lookup, synthetic input, and early workflow automation.

![ED Control Room](docs/assets/control-room.png)

See [docs/STATUS.md](docs/STATUS.md) for the maintained status, validation notes, and next recommended work.

## Contents

- [Start Here](#start-here)
- [Control Room Highlights](#control-room-highlights)
- [Haul Workflow](#haul-workflow)
- [Current Surface](#current-surface)
- [Primary Entrypoints](#primary-entrypoints)
- [Platform Validation](#platform-validation)
- [Galaxy Map Binding Requirement](#galaxy-map-binding-requirement)
- [Bindings Utility](#bindings-utility)
- [Repo Layout](#repo-layout)
- [Docs Map](#docs-map)
- [Development](#development)

## Start Here

- run `uv sync`
- run `uv run python3 control_room.py`
- Important Note:
    - after you fire off a ship-affecting command, make sure to switch back to Elite Dangerous; EDControlRoom works by sending keyboard input to the game window
    - those commands wait `5` seconds by default, so you have time to switch back to Elite before the first key press
    - if you are remotely connected to the shell and do not need that safety pause, use `instant` in Control Room to toggle the delay off or back on
    
Once you have control room up and running:
- use `haul` to haul from A <-> B as the main end-to-end workflow
- for setup details, platform-specific notes, and more commands, continue to [docs/getting-started/quickstart.md](docs/getting-started/quickstart.md)
- use [docs/operators/control-room.md](docs/operators/control-room.md) for day-to-day operation
- use [docs/operators/bindings-files.md](docs/operators/bindings-files.md) for `.binds` backup / restore / preset apply

## Control Room Highlights

- `control_room.py` is the primary operator surface
- `haul` is the strongest current operator flow and runs the active two-way haul loop
- `replay` / `Ctrl-R` reopens recent commands, including haul setups
- one saved default haul setup persists across restarts
- Control Room mirrors consumed journal events into `artifacts/control-room.log`
- after you fire off a ship-affecting command, switch back to Elite while the default `5` second launch delay runs
- `instant` toggles that delay on or off for future commands when you are operating from a remote shell session or otherwise do not need the safety pause

Interrupt behavior during `haul` is haul-aware: the first `Ctrl-C` or `Ctrl-D` queues a stop after the current station-1 return sale and before the next buy. A second interrupt cancels immediately.

## Haul Workflow

`haul` is the strongest current end-to-end routine and the clearest example of what the active runtime is for.

It is built to take the boring bits off the commander: from the moment you drop near a station, it handles the repeatable station-side work for you, including requesting docking, working through station services, buying or selling cargo, refuel and repair steps, setting the route for the next leg, leaving the station, clearing mass lock, and then priming the FSD automatically.

There is no auto-alignment. Instead, once the ship is clear and the drive is primed, EDControlRoom uses TTS to call the commander by title or name and say the ship is ready to jump, which is the cue for commanders to take over for alignment and the next jump.

That makes it directly useful for high-volume A-to-B cargo work such as community goal hauling loops, where the repetitive station-to-station trading cycle is the part worth automating and the commander can stay focused on the parts that still benefit from human attention.

Around that primary flow, the active routine surface also includes `dock`, `undock`, `jump`, `buy`, `sell`, and `dest`.

These are built to be manually exercised against a live Elite session, not left unattended.

## Current Surface

What works today:

- shared journal parsing, bindings lookup, and platform input/runtime plumbing across supported targets
- live-validated operator paths on macOS via CrossOver and on Windows via community testing from CMDR VRYAE
- journal-driven `haul`, `jump`, `dock`, `undock`, `buy`, `sell`, and `dest` flows
- a live Control Room TUI with ship status, activity log, market panel, replay history, saved default haul setup, and repo-local journal-event logging

What is not done:

- the legacy CV-driven align loop is still not ported into the active runtime

## Primary Entrypoints

- `uv run python3 control_room.py`
- `uv run python3 run_routine.py --routine haul_loop`
  This is the two-way haul routine used by Control Room.
- `uv run python3 diagnostics.py`
- `uv run python3 ship_controls.py --action SetSpeedZero --delay-seconds 3`
- `uv run python3 bindings_files.py`
  Lists, backs up, restores, and can replace the active `.binds` file from shipped presets.

## Platform Validation

- macOS: live-validated with Elite running through CrossOver by myself, @NicholasClooney
- Windows: live-validated by community member CMDR VRYAE
- Linux: runtime paths exist, but no live validation yet

## Galaxy Map Binding Requirement

The current galaxy-map automation depends on Elite having arrow-key secondary
bindings on these four actions:

- `UI_Up` -> `UpArrow`
- `UI_Down` -> `DownArrow`
- `UI_Left` -> `LeftArrow`
- `UI_Right` -> `RightArrow`

Keep your normal primary bindings as needed, but make sure those arrow-key
secondaries are present in the live `.binds` file. On the current Elite setup,
`W/A/S/D` pans the galaxy map view, while arrow-key `UI_*` bindings move the
map/menu cursor. Without those secondary arrow bindings, `dest` / galaxy-map
automation will not navigate the map menus correctly.

## Bindings Utility

`bindings_files.py` is the operator helper for `.binds` file management.

Examples:

```sh
uv run python3 bindings_files.py
uv run python3 bindings_files.py backup
uv run python3 bindings_files.py restore
uv run python3 bindings_files.py apply-default
```

See [docs/operators/bindings-files.md](docs/operators/bindings-files.md) for the full command surface.

Note: `apply-default` is implemented and covered by unit tests, but it has not yet been live-validated against a real Elite session. If it does not behave as expected on your setup, please open an issue or report the exact command and resulting file state.

## Repo Layout

- `control_room.py`, `run_routine.py`, `diagnostics.py`, `ship_controls.py`: active operator and validation entrypoints
- `edap/`: active runtime code
- `tools/scratch/`: exploratory probes and one-off validation helpers
- `archive/legacy-windows/`: Windows-era behavior reference code, kept for historical context only

## Docs Map

- [docs/getting-started/quickstart.md](docs/getting-started/quickstart.md)
  Setup plus first commands.
- [docs/operators/control-room.md](docs/operators/control-room.md)
  Main operator workflow, haul behavior, replay/history, and interrupt semantics.
- [docs/operators/bindings-files.md](docs/operators/bindings-files.md)
  `.binds` backup, restore, and shipped preset apply flows.
- [docs/operators/manual-journal-routine-testing.md](docs/operators/manual-journal-routine-testing.md)
  Low-level routine validation outside Control Room.
- [docs/diagnostics/cli-reference.md](docs/diagnostics/cli-reference.md)
- [docs/diagnostics/bindings-reference.md](docs/diagnostics/bindings-reference.md)
- [docs/README.md](docs/README.md)

## Development

Use the repo `uv` environment for tests:

```sh
uv run python3 -m unittest discover -s tests
```

For commits, use Conventional Commits.

Examples:

- `feat: add config loader`
- `refactor: split platform adapters from autopilot logic`
- `docs: update macos roadmap`
- `fix: validate missing journal path`
