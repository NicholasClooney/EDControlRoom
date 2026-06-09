# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-09

- Documented Elite preset locations and controller-token format under CrossOver in `docs/research/0006-elite-bindings-preset-locations.md`: built-in presets come from the installed `Products/elite-dangerous-odyssey-64/ControlSchemes` folder, user-editable profiles still live under `AppData/Local/.../Options/Bindings`, and controller bindings are stored as symbolic `Device`/`Key` pairs with USB identity data in `DeviceMappings.xml`.
- `bindings_files.py` now supports `restore` from repo-local backups and `apply-default` from shipped `ControlSchemes` presets; both flows save a fresh backup before overwriting the active file, `restore` supports numbered or interactive selection, and preset application preserves the active file's `PresetName`/version metadata. Verified with `uv run python3 -m unittest discover -s tests` (`310` tests, `0.145s`).
- The interactive `bindings_files.py` selectors now cancel cleanly on `Ctrl-C` and support typed prefix filtering in addition to up/down selection and numeric selection; verified with `uv run python3 -m unittest discover -s tests` (`313` tests, `0.137s`).
- Added `docs/operators/bindings-files.md` plus a README mention for `bindings_files.py`, including an explicit note that `apply-default` is not yet live-validated and should be reported if it behaves unexpectedly.
- Changed Windows bindings auto-detection to match macOS/Linux: `default_bindings_file()` now selects the newest `.binds` file by modification time, with test coverage proving filename sort order no longer decides the winner.
