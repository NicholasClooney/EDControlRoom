# CLI Reference

Low-level validation and utility entrypoints live at the repo root. Exploratory probes live under `tools/scratch/`.

## Diagnostics

```sh
uv run python3 diagnostics.py
uv run python3 diagnostics.py --capture-screen
uv run python3 diagnostics.py --send-test-key --test-key j --delay-seconds 5
```

`diagnostics.py` validates config loading, journal path resolution, bindings parsing, screen capture, and synthetic input delivery.

`--send-test-key` is a raw input-backend check. It sends the literal key you pass through the active platform backend and does not look up an Elite action from the `.binds` file. Use it to answer "can EDAP inject input at all on this machine?" not "does `SetSpeedZero` resolve and fire correctly?".

## Bindings

```sh
uv run python3 check_bindings.py
uv run python3 check_bindings.py --verbose
uv run python3 check_bindings.py --json
uv run python3 set_binding.py PitchDownButton --show
```

See [bindings-reference.md](bindings-reference.md) for the action names the runtime depends on.

## Journal

```sh
uv run python3 watch_journal.py
uv run python3 run_routine.py --routine jump --log-events
```

## Ship Controls

```sh
uv run python3 ship_controls.py --action SetSpeedZero --delay-seconds 3
uv run python3 ship_controls.py --sequence "SetSpeedZero; RollLeftButton total=0.45; SetSpeed100 delay=5"
```

## Scratch Probes

```sh
uv run python3 tools/scratch/scratch_cv.py --save-debug /tmp/cv-debug.png
uv run python3 tools/scratch/scratch_rebake.py destination --delay 3 --open
uv run python3 tools/scratch/scratch_market.py --raw
uv run python3 tools/scratch/scratch_cgevent.py x --modifier ctrl --hold 0.2
```
