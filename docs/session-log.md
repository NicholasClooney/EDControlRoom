# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-09

- Control-room startup binding warnings now show the in-game control label plus Controls-menu path for missing routine actions, and binding lookup now reports mouse-only versus joystick/controller-only cases distinctly; keyboard `Secondary` still overrides keyboard `Primary`, but non-keyboard slots never override a keyboard bind. Verified with `uv run python3 -m unittest tests/test_binding_lookup.py tests/test_control_room.py`.
- Control-room startup binding warnings now ignore the currently unused maneuver actions `RollLeftButton`, `RollRightButton`, `PitchUpButton`, `PitchDownButton`, `YawLeftButton`, and `YawRightButton`; `docs/STATUS.md` now calls out that any future routine or CV/alignment work that starts using them must remove that ignore list in the same change. Verified with `uv run python3 -m unittest tests/test_control_room.py`.
- Market buy/sell now reset commodity trade-dialog focus with `UI_Left x3` plus `UI_Up x3` immediately after opening a commodity, reducing dependence on where the game initially places the cursor; verified with `uv run python3 -m unittest tests/test_routines.py`.
