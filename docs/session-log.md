# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-08

- Market sell now keeps the original demand-sorted SELL order and only injects the requested hidden-but-sellable target row into that order when needed, fixing the cursor index path for cargo like `Food Cartridges` without changing the base list model.
- Market sell now sends `UI_Back x4` to reset the menu stack before each attempt, requires a current docked journal state before it starts, and re-checks that docked state after the trade back-out.
- `ShipControls` now interprets `repeat>1` as separate taps with built-in spacing instead of one collapsed repeated dispatch; full verification passed with `296` unittest cases via `uv run python3 -m unittest discover -s tests`.
- Repeat pacing now lives in `ActionDispatcher` instead of only `ShipControls`, so direct dispatcher callers and `submit_text` also emit separate delayed taps; full regression coverage was updated around both layers.
- Release prep for `v1.4.0` now also updates `AGENTS.md` to require `uv sync` plus the resulting `uv.lock` commit whenever `[project].version` changes.
- Control-room command parsing now treats only the final token of `buy`/`sell` as an amount candidate, so multi-word commodities like `buy food cartridges` default to `MAX` correctly; unknown and invalid commands are also recorded into saved replay history now.
- Market `buy ... max` now scales the `UI_Right` hold from free cargo space instead of using a fixed 10-second press; the new `controls.market_buy_hold_seconds_per_ton` setting defaults to `0.01` and falls back to the old cap when cargo space cannot be derived from `Cargo.json` plus journal capacity.
- Market buy/sell now checks station supply or demand against cargo capacity, logs normal levels, warns plus TTS-announces critically low levels, and makes the threshold configurable via `controls.market_critical_level_multiplier`.
- Control room reads `Status.json` destination fields into `SHIP STATUS`, displays them as `Destination: system/body/name`, and refreshes that snapshot on a configurable `control_room.status_refresh_seconds` cadence (default `2.0`). Live re-check showed the destination row also appears in supercruise.
- Prepared `v1.3.0` for release after confirming the post-`v1.2.0` two-way hauling, queued TTS, control-room telemetry/status, and cross-platform runtime coverage changes against the full unittest suite (`283` passing via `uv run python3 -m unittest discover -s tests`).
- Clarified release procedure in `AGENTS.md`: release prep must also update `pyproject.toml` so `[project].version` matches the semantic tag version without the leading `v`.
- Windows `SendInput` failures reproduced by a user on admin-to-admin Notepad led to a backend fix: `edap.platform.input.windows` now uses the full Win32 `INPUT` union shape and reports `GetLastError()` on failure; verified with `uv run python3 -m unittest tests/test_windows_input.py` and `uv run python3 -m unittest tests/test_runtime.py`.
- Control room startup now logs the resolved bindings file path/source and emits inline warnings for any missing or unsupported routine action mappings; verified with `uv run python3 -m unittest tests/test_control_room.py` and `uv run python3 -m unittest tests/test_check_bindings_cli.py`.
- Parked a future validation slice in `STATUS.md`: true cross-platform live input verification should use a small Python receiver app on self-hosted desktop runners to validate modifier/key event order, rather than relying on hosted CI text-entry checks alone.
