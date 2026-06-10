# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-10

- Added `control_room.activity_log_max_lines` to the Control Room runtime surface: `ActivityLog` now receives the configured retention limit by default, and `ControlRoomApp(..., activity_log_max_lines=...)` can still inject an explicit override for tests or alternate launch surfaces.
- Bounded queued TTS backlog in-process and coalesced stale queued repeats by announcement type once speech is already in flight, so long sessions keep the latest relevant callout without unbounded queue growth.
- Buffered Control Room's `artifacts/control-room.log` mirror so steady-state journal appends flush every 20 events instead of every event, while shutdown still forces a final flush before close.
- Final integrated verification: `uv run python3 -m unittest discover -s tests` (`354` tests, `0.142s`).
