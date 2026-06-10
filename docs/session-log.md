# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-10

- Switched release/update metadata to the moved GitHub repository `TheClooneyCollection/EDControlRoom`, updated test release URLs to match, and kept the full suite green afterward.
- Updated release-please to patch the root `EDControlRoom` version inside `uv.lock` via TOML `jsonpath`, renamed the Python distribution/runtime metadata from `edautopilot` to `EDControlRoom`, refreshed the Control Room update-status strings/tests, and rechecked the full suite at `354 tests in 0.131s`.
- Added `.github/workflows/release-please.yml` plus manifest/config files so releases are opened as PRs against protected `main`; seeded the manifest at `1.7.3`, documented the optional `RELEASE_PLEASE_TOKEN` secret for CI-on-release-PRs, and rechecked the full suite at `354 tests in 0.134s`.
- Added PR-title guidance to `AGENTS.md` and a `.github/pull_request_template.md`: normal PRs use Conventional Commit prefixes, `dev` -> `main` promotions default to `chore: promote dev to main`, and `release: ...` is reserved for versioned release PRs.
- Increased the market commodity-view focus-reset safeguard from `UI_Left/UI_Up x3` to `x5` for both buy and sell flows, updated the routine tests to match, and rechecked timing after the full suite still passed at `354 tests in 0.275s` with no single dominant slow test in `tools/report_test_timing.py`.
- Replaced lingering project shorthand in active docs and user-facing CLI text with `EDControlRoom`, including quickstart/diagnostics/manual-testing docs, the TTS helper description, and one market-routine comment.
- Renamed the active docs surface to `EDControlRoom` and removed lingering old-project branding from README, AGENTS release-title guidance, and the maintained Control Room operator doc.
- Reviewed haul station-automation assumptions: current flow hard-waits on `DockingGranted`/`Docked` for arrival and `Music` `NoTrack` after `Undocked` for launch clearance; routing and FSD engage themselves are independent of auto-alignment.
- Tightened README and Control Room haul docs to describe the commander-facing handoff more explicitly: EDControlRoom handles post-drop station chores, primes the FSD after station clearance, then uses TTS as the ready-to-jump cue.
- Confirmed a CrossOver/Elite bindings caveat for future troubleshooting: if a shared `Custom` `.binds` preset contains controller mappings, Elite may refuse to surface/load that preset until the mapped controller is connected or otherwise visible to the runtime.
- Preemptive trim of `docs/STATUS.md` (Current Snapshot, Active Capabilities, Key Caveats each kept to top 5 newest bullets) and a full session-log reset to status-archive, restoring headroom before the next handoff.
