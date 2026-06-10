# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-10

- Tightened the callback refactor after review: removed production default no-op callback params from routine entrypoints, restricted no-op helper usage to tests/wrappers, updated `AGENTS.md` to codify that rule, and re-ran full unittest verification.
- Callback refactor follow-up: added shared routine no-op callback helpers, made routine-layer progress/announcement types concrete instead of `Optional[...]`, wrapped silent routine tests through explicit no-op adapters, and re-verified the full suite at `354` tests in `0.167s`.
- Compacted `docs/STATUS.md` to restore headroom and recorded the callback-typing rule: keep progress/announcement callbacks non-optional when production callers always pass them, and use explicit no-op callbacks in tests instead of `None`.
- Reworded the repeated focus/delay guidance in `README.md` and `docs/operators/control-room.md` to be more operator-friendly: fire the command, switch back to Elite during the 5-second delay, or use `instant` when running from a remote shell.
- Added repeated operator-facing focus/delay guidance to `README.md` and `docs/operators/control-room.md`: EDAP needs the game window focused because it sends keyboard input, Control Room waits 5 seconds before ship-affecting commands by default, and `instant` toggles that delay for remote-shell use.
- Refined `docs/operators/control-room.md` for operators: added the shipped screenshot, documented the most-used keyboard shortcuts up front, and replaced the old developer-style notes block with shorter user-facing behavior notes.
- Tightened `docs/getting-started/quickstart.md`: moved Control Room launch ahead of probe commands, collapsed repeated config override guidance into one shared note, and reframed `watch_journal.py` / `ship_controls.py --action SetSpeedZero` as optional troubleshooting checks with clearer behavior notes.
- Cut release prep for `v1.7.3`: bumped package metadata, refreshed maintained status/session notes, and targeted the post-`v1.7.2` runtime-hardening slice (bounded queued TTS/session growth, buffered journal-log flushes, injectable version source).
- Added `control_room.activity_log_max_lines` to the Control Room runtime surface: `ActivityLog` now receives the configured retention limit by default, and `ControlRoomApp(..., activity_log_max_lines=...)` can still inject an explicit override for tests or alternate launch surfaces.
- Bounded queued TTS backlog in-process and coalesced stale queued repeats by announcement type once speech is already in flight, so long sessions keep the latest relevant callout without unbounded queue growth.
- Buffered Control Room's `artifacts/control-room.log` mirror so steady-state journal appends flush every 20 events instead of every event, while shutdown still forces a final flush before close.
- Final integrated verification: `uv run python3 -m unittest discover -s tests` (`354` tests, `0.142s`).
