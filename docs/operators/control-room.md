# Control Room

`control_room.py` is the main live operator surface.

Run it with:

```sh
uv run python3 control_room.py
uv run python3 control_room.py --market aluminium
```

If `config.toml` exists in the repo root, EDControlRoom loads it automatically. Create one only when you need explicit overrides beyond the built-in auto-detection.

EDControlRoom works by sending keyboard input to Elite Dangerous. After you fire off any command that should affect the ship or UI, switch back to the game window before the delay expires.

![Control Room screenshot](../assets/control-room.png)

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
- haul is aimed at commanders who want the station-side repetition handled for them: after a drop near station it requests docking, runs station services, buys or sells cargo, refuels, repairs, routes the next leg, launches, clears mass lock, and primes the FSD
- haul does not auto-align for the next jump; after station clearance it uses TTS to call the commander by title or name and announce that the ship is ready to jump as the handoff cue
- haul resumes from current journal and sidecar state rather than assuming a fresh start
- one default haul setup can be saved and reused across restarts
- `replay` / `Ctrl-R` is the quickest way to relaunch recent haul commands or rerun a saved pattern without retyping it

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

## Keybinds

- `Ctrl-R` opens replay/history from the command bar.
- `Ctrl-C` stops the app when idle. During `haul`, the first press requests a safe stop at the next station-1 boundary after the return sale, and the second press cancels immediately.
- `Ctrl-D` behaves the same as `Ctrl-C`.

## Useful Behavior

- Ship-affecting commands wait `5` seconds before starting by default, so you have time to switch back to Elite before EDControlRoom sends any key presses.
- `instant`, `instant on`, and `instant off` control that default launch delay for future commands. This is mainly useful when you are remotely connected to the shell and do not need the normal safety pause.
- Startup writes version information into `ACTIVITY`, and when update checks are enabled it also tells you if a newer EDControlRoom release is available.
- In replay/history, typing applies a simple prefix filter and `Backspace` removes characters from that filter.
- `sell` with no explicit item falls back to `Cargo.json` if the in-memory cargo manifest is empty.
- Cross-session command history and one saved default haul profile are persisted in `.control_room_state.json` by default.
- Consumed journal events are mirrored into `artifacts/control-room.log`, so you can inspect what Control Room saw during a run.
