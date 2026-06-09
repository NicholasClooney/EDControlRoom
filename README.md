# EDAutopilot MK II

Multiplatform Elite Dangerous automation tooling focused on a shared runtime across macOS, Windows, and Linux. The active runtime is live-validated on macOS with Elite running through CrossOver by myself, @NicholasClooney, and the Windows path is now also live-validated by community member CMDR VRYAE. Linux remains unvalidated.

The current operator surface is [`control_room.py`](control_room.py). The project is not a full autopilot yet; it is a live runtime and routine stack built around journal parsing, bindings lookup, synthetic input, and early workflow automation.

![ED Control Room](docs/assets/control-room.png)

See [docs/STATUS.md](docs/STATUS.md) for the maintained status, validation notes, and next recommended work.

## Current Surface

What works today:

- shared journal parsing, bindings lookup, and platform input/runtime plumbing across supported targets
- live-validated operator paths on macOS via CrossOver and on Windows via community testing from CMDR VRYAE
- journal-driven `haul`, `jump`, `dock`, `undock`, `buy`, `sell`, and `dest` flows
- a live Control Room TUI with ship status, activity log, market panel, replay history, and saved default haul setup

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

## Routine Overview

`haul` is the strongest current end-to-end routine and the clearest example of what the active runtime is for. It automates a repeatable trade loop between two stations: resuming from the current game state, docking when needed, navigating station services, buying the target commodity, launching, plotting the return destination, and selling cargo at the other end.

That makes it directly useful for high-volume A-to-B cargo work such as the current community goal hauling loops, where the repetitive station-to-station trading cycle is the part worth automating.

Around that primary flow, the active routine surface also includes `dock`, `undock`, `jump`, `buy`, `sell`, and `dest`.

These are built to be manually exercised against a live Elite session running through CrossOver, not left unattended.

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
  Includes current macOS and Windows setup paths.
- [docs/operators/control-room.md](docs/operators/control-room.md)
- [docs/operators/bindings-files.md](docs/operators/bindings-files.md)
- [docs/operators/manual-journal-routine-testing.md](docs/operators/manual-journal-routine-testing.md)
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
