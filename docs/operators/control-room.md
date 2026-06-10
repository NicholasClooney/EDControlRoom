# Control Room

`control_room.py` is the main live operator surface.

Run it with:

```sh
uv run python3 control_room.py
uv run python3 control_room.py --market aluminium
```

If `config.toml` exists in the repo root, EDAP loads it automatically. Create one only when you need explicit overrides beyond the built-in auto-detection.

## What It Is

- primary operator surface for current routine work
- best-supported end-to-end path is `haul`
- one routine runs at a time

## Panels

- `SHIP STATUS`: commander, system, station, flight state, fuel, credits, cargo, `Destination` from `Status.json` (`system/body/name`), and journal `FSD target`
- `ACTIVITY`: live event log plus routine progress lines
- `MARKET`: commodity table from `Market.json`, with filtering and lock/unlock controls

## Main Commands

- `dock`
- `undock`
- `jump`
- `buy <item> [N|max]`
- `sell`
- `sell <item> [N|max]`
- `haul [commodity]`
- `dest <system>`
- `set_dest <system>`

## Haul

- `haul [commodity]` runs the active two-way haul loop used by `run_routine.py --routine haul_loop`
- haul resumes from current journal and sidecar state rather than assuming a fresh start
- one default haul setup can be saved and reused across restarts
- `replay` / `Ctrl-R` is the quickest way to relaunch recent haul commands

Interrupt behavior during `haul` is special:

- first `Ctrl-C` or `Ctrl-D`: finish the current run and stop at station 1 after the return sale, before the next buy
- second `Ctrl-C` or `Ctrl-D`: cancel immediately

## Other Commands

- `market filter <name>`
- `market`
- `market clear`
- `market lock`
- `market unlock`
- `replay`
- `commands`
- `help [command]`
- `q`, `quit`, `exit`

## Notes

- Startup logs a current-version line in `ACTIVITY`; when the GitHub check confirms the local build is current it says `Currently running latest version (...)`, otherwise it falls back to `Currently running version ...`.
- When `control_room.check_for_updates = true` (default), startup also performs a short GitHub latest-release check and adds a separate `A newer ED AutoPilot Mk II release is available: ...` line only when a newer release exists.
- `control_room.status_refresh_seconds` controls how often control room re-reads `Status.json` and refreshes market/haul side state; default `2.0`.
- Live observation on 2026-06-08: `Status.json` `Destination` does show in `SHIP STATUS` during supercruise, and also appears in normal space after dropping from supercruise, while docking, and while docked.
- `Ctrl-R` opens replay/history from the command bar.
- In replay/history, typing applies a simple prefix filter; `Backspace` deletes the filter.
- `Ctrl-C` and `Ctrl-D` do not close the TUI while a routine is active; when idle they exit the app.
- `sell` with no explicit item falls back to `Cargo.json` if the in-memory cargo manifest is empty.
- Cross-session command history and one saved default haul profile are persisted in `.control_room_state.json` by default.
- Consumed journal events are mirrored into `artifacts/control-room.log`.
