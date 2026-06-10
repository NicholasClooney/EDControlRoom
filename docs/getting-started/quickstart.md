# Quickstart

## Setup

`config.example.toml` is the full reference config. Create a local `config.toml` only if you want overrides; EDAP auto-loads it when present, and otherwise falls back to platform defaults plus auto-detection.

When you do create `config.toml`, keep it minimal:

- Set `paths.journal_dir` and `paths.bindings_file` only if auto-detection is not enough on this machine.
- Leave `runtime.platform` unset unless you want to make the backend choice explicit in a shared config. When omitted, it defaults to the host OS.

### macOS + CrossOver

1. Make sure Terminal has macOS Accessibility permission, and Screen Recording permission if you plan to use capture-based diagnostics.
2. Start Elite Dangerous through CrossOver.

### Windows with `uv`

1. Install Python 3.12 and `uv`.
2. Run `uv sync`.
3. Start Elite Dangerous.

### Windows without `uv`

1. Install Python 3.12.
2. Create a virtual environment:

```sh
python -m venv .venv
```

3. Activate it:

```sh
.venv\Scripts\activate
```

4. Install runtime deps:

```sh
pip install -r requirements.txt
```

5. Start Elite Dangerous.

### Linux

1. Install Python 3.12 and `uv`.
2. Install `xdotool` if you want synthetic key input support.
3. Start Elite Dangerous through Steam/Proton.

On Linux, prefer explicit `paths.journal_dir` and `paths.bindings_file` only when the built-in Steam Proton probing for app ID `359320` is not enough on this machine.

Minimal example:

```toml
[paths]
journal_dir = ""
bindings_file = ""

[tts]
title_mode = "custom"
title = "captain"
```

Linux input is currently implemented through `xdotool`, so treat it as X11-oriented and verify it locally before relying on routines. Wayland behavior is unverified.

## Start Control Room

Control Room is the primary operator surface for current routine work, so start there first after installation.

With `uv`:

```sh
uv run python3 control_room.py
```

If your Windows shell does not provide `python3`, use `uv run python ...` instead.

Without `uv`:

```sh
python control_room.py
```

For day-to-day usage, haul behavior, replay/history, and interrupt semantics, see [../operators/control-room.md](../operators/control-room.md).

## If Something Is Not Working

Use these checks only when you need to troubleshoot input, journal detection, or game integration.

With `uv`:

```sh
uv run python3 watch_journal.py
uv run python3 ship_controls.py --action SetSpeedZero --delay-seconds 3
```

If your Windows shell does not provide `python3`, use `uv run python ...` instead.

Without `uv`:

```sh
python watch_journal.py
python ship_controls.py --action SetSpeedZero --delay-seconds 3
```

- `watch_journal.py` tails the Elite journal and prints events as they arrive. Run it only while the game is open, otherwise nothing new will appear.
- `ship_controls.py --action SetSpeedZero --delay-seconds 3` waits three seconds, then presses the key currently bound to Elite's `SetSpeedZero` action. Expect your throttle-zero keybind to fire in game.

If journal or bindings auto-detection still looks wrong after that, add explicit `paths.journal_dir` and `paths.bindings_file` overrides in `config.toml`.

## Routine Harness

```sh
uv run python3 run_routine.py --routine jump --delay-seconds 5
uv run python3 run_routine.py --routine dock --delay-seconds 5 --log-events
uv run python3 run_routine.py --routine haul_loop
```

`haul_loop` is the current two-way haul routine and matches the Control Room haul path.

Windows equivalents:

```sh
uv run python run_routine.py --routine jump --delay-seconds 5
python run_routine.py --routine jump --delay-seconds 5
```

Linux equivalent:

```sh
uv run python3 run_routine.py --routine jump --delay-seconds 5
```

For current supported manual validation flows, see [../operators/manual-journal-routine-testing.md](../operators/manual-journal-routine-testing.md).

For `.binds` backup, restore, or shipped preset apply, see [../operators/bindings-files.md](../operators/bindings-files.md).
