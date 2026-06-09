# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-09

- Control-room startup binding warnings now ignore the currently unused maneuver actions `RollLeftButton`, `RollRightButton`, `PitchUpButton`, `PitchDownButton`, `YawLeftButton`, and `YawRightButton`; `docs/STATUS.md` now calls out that any future routine or CV/alignment work that starts using them must remove that ignore list in the same change. Verified with `uv run python3 -m unittest tests/test_control_room.py`.
