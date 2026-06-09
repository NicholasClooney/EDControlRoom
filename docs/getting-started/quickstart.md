# Quickstart

## Setup

`config.example.toml` is the full reference config. Create a local `config.toml` only if you want overrides; EDAP auto-loads it when present, and otherwise falls back to platform defaults plus auto-detection.

### macOS + CrossOver

1. Optional: create `config.toml` only if you need local overrides.
2. Set `paths.journal_dir` and `paths.bindings_file` explicitly only if auto-detection is not enough on this machine.
3. Leave `runtime.platform` unset unless you want to make the backend choice explicit in a shared config. When omitted, it defaults to the host OS.
4. Make sure Terminal has macOS Accessibility permission, and Screen Recording permission if you plan to use capture-based diagnostics.
5. Start Elite Dangerous through CrossOver.

### Windows with `uv`

1. Install Python 3.12 and `uv`.
2. Run `uv sync`.
3. Optional: create `config.toml` only if you need local overrides.
4. Leave `runtime.platform` unset unless you want to make the backend choice explicit in a shared config. When omitted, it defaults to the host OS.
5. Set `paths.journal_dir` and `paths.bindings_file` explicitly only if auto-detection is not enough on this machine.
6. Start Elite Dangerous.

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

5. Optional: create `config.toml` only if you need local overrides.
6. Leave `runtime.platform` unset unless you want to make the backend choice explicit in a shared config. When omitted, it defaults to the host OS.
7. Set `paths.journal_dir` and `paths.bindings_file` explicitly only if auto-detection is not enough on this machine.
8. Start Elite Dangerous.

### Linux

1. Install Python 3.12 and `uv`.
2. Install `xdotool` if you want synthetic key input support.
3. Optional: create `config.toml` only if you need local overrides.
4. Leave `runtime.platform` unset unless you want to make the backend choice explicit in a shared config. When omitted, it defaults to the host OS.
5. Prefer explicit `paths.journal_dir` and `paths.bindings_file` only when the built-in Steam Proton probing for app ID `359320` is not enough on this machine.
6. Start Elite Dangerous through Steam/Proton.

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

## First Checks

On macOS:

```sh
uv run python3 diagnostics.py
uv run python3 watch_journal.py
uv run python3 ship_controls.py --action SetSpeedZero --delay-seconds 3
```

On Windows with `uv`:

```sh
uv run python diagnostics.py --send-test-key
uv run python ship_controls.py --action SetSpeedZero --delay-seconds 3
```

On Windows without `uv`:

```sh
python diagnostics.py --send-test-key
python ship_controls.py --action SetSpeedZero --delay-seconds 3
```

On Linux:

```sh
uv run python3 diagnostics.py --send-test-key
uv run python3 ship_controls.py --action SetSpeedZero --delay-seconds 3
```

Validate `diagnostics.py --send-test-key` first on Windows. That proves the `SendInput` path reaches Elite before you debug bindings or routines.
Validate `diagnostics.py --send-test-key` first on Linux too. That proves the `xdotool` path reaches the game before you debug bindings or routines.

`diagnostics.py --send-test-key` only checks raw synthetic input delivery for a literal key such as `space` or `j`. It does not validate Elite action lookup from the bindings file. After that low-level check passes, use `check_bindings.py` to verify action resolution and `ship_controls.py --action ...` to verify a resolved Elite action in game.

## Main Runtime

```sh
uv run python3 control_room.py
```

Windows equivalents:

```sh
uv run python control_room.py
python control_room.py
```

Linux equivalent:

```sh
uv run python3 control_room.py
```

Control Room is the primary operator surface for current routine work.

For day-to-day usage, haul behavior, replay/history, and interrupt semantics, see [../operators/control-room.md](../operators/control-room.md).

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
