# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-09

- Prepared and verified release `v1.7.1`: rolled up the docked-location bootstrap fix, configured-title hyperspace-arrival TTS fix, nested control-config sections, digit-aware location TTS normalization, and the README/docs surface tightening. Verified with `uv run python3 -m unittest discover -s tests` (`335` tests, `0.161s`).
- Added an `AGENTS.md` rule to keep the hand-written README TOC updated whenever top-level README sections move; GitHub's automatic Outline menu exists, but it does not replace the inline TOC block.
- Reshaped `README.md` so `Start Here` now leads with `uv sync` plus `uv run python3 control_room.py`, points deeper setup to `docs/getting-started/quickstart.md`, and moves the Control Room / haul explanation above the broader repo overview.
- TTS now normalizes `3+` digit runs in spoken system/station names so callouts like `HIP 58412` are rendered as `HIP 5 8 4 1 2` while shorter tags like `B13-2` remain intact; verified with `uv run python3 -m unittest discover -s tests` (`333` tests, `0.158s`).
- `speak.py` now supports `--system-name` and `--station-name` so the CLI smoke test can exercise the same digit-splitting name normalization as in-app TTS without changing generic raw-text speech; verified with `uv run python3 -m unittest discover -s tests` (`335` tests, `0.154s`).

## 2026-06-10

- Control Room startup now logs the current app version in `ACTIVITY` and can perform a short GitHub latest-release check to gently notify operators only when a newer release exists; added `control_room.check_for_updates = true|false` plus reusable `edap.version` helpers. Verified with `uv run python3 -m unittest discover -s tests` (`343` tests, `0.153s`).
- Refined the startup wording so the version line says `Currently running latest version (...)` only when GitHub confirms the local release is current, otherwise it says `Currently running version ...` and adds a separate `A newer ED AutoPilot Mk II release is available: ...` line. Verified with `uv run python3 -m unittest discover -s tests` (`344` tests, `0.141s`).
