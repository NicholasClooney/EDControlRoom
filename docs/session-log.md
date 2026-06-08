# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-08

- Market buy/sell now checks station supply or demand against cargo capacity, logs normal levels, warns plus TTS-announces critically low levels, and makes the threshold configurable via `controls.market_critical_level_multiplier`.
- Control room reads `Status.json` destination fields into `SHIP STATUS`, displays them as `Destination: system/body/name`, and refreshes that snapshot on a configurable `control_room.status_refresh_seconds` cadence (default `2.0`). Live re-check showed the destination row also appears in supercruise.
