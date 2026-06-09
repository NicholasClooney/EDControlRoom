# Project Status

_This is the startup handoff document for the repo. Keep it current, compact, and biased toward what the next session needs immediately. Hard limit: 80 lines. If an update would push this file past the limit, move displaced detail to `status-archive.md` or a more specific doc, then trim this file back down._

Last updated: 2026-06-09

## Current Snapshot

- Plan 0001 (macOS MVP portability) is complete. Shared runtime, config loading, journal parsing, bindings lookup, and synthetic input are in place and live-validated on macOS + CrossOver.
- Windows now has early real-world validation from CMDR VRYAE, so the platform story is macOS-primary with initial Windows confirmation rather than macOS-only live validation.
- Current work is follow-up, not a rewrite: journal-driven routines, two-way hauling, CV/capture validation, and operator diagnostics.
- Stable release `v1.6.0` now packages the recent two-way haul resume fixes, docking follow-up polish, and Control Room activity-log follow behavior.
- `control_room.py` is the primary operator surface. `run_routine.py`, `ship_controls.py`, `diagnostics.py`, `speak.py`, and the journal/bindings helpers remain the main manual-validation tools.
- `bindings_files.py` now provides a quick operator utility to list `.binds` files from the detected bindings folder, copy them into the repo-local gitignored `backup/bindings/` folder, restore from numbered or interactive backup selections, and apply shipped default presets onto the active custom file after confirmation while saving a safety backup first.
- Operator-facing usage for `bindings_files.py` now lives in `docs/operators/bindings-files.md`, and `README.md` now calls out that `apply-default` is implemented but not yet live-validated against a real Elite session.
- Windows bindings auto-detection now matches macOS/Linux by selecting the newest `.binds` file by modification time instead of the lexicographically last filename.
- Web-control UI research is now captured in `docs/research/0005-web-control-ui-options.md`, including the current NiceGUI-first prototype recommendation and the iPhone Safari LAN-HTTP caveat from NiceGUI issue `#5802`.
- Elite preset-location research is now captured in `docs/research/0006-elite-bindings-preset-locations.md`, confirming that CrossOver user bindings live under `Options/Bindings` while Frontier's built-in presets come from the installed `ControlSchemes` folder, and that controller bindings are stored as logical `Device`/`Key` tokens backed by `DeviceMappings.xml`.

## Active Capabilities

- Journal/runtime: journal tailing, bindings lookup, runtime construction, and shared platform seams are working.
- Control Room: live Textual UI with ship status, market panel, haul stats, replay/history, persisted state, routine dispatch, queued cross-platform TTS announcements, and a repo-local `artifacts/control-room.log` journal-event mirror for sessions where the standalone watcher is not running.
- Routines: `jump`, `dock`, `undock`, market buy/sell, galaxy-map destination setting, and the two-way haul loop live under `edap/routines/`.
- Hauling: `edap.routines.haul_loop` now aliases the two-way implementation directly; the older one-way haul codepath is gone.
- Two-way haul resume now uses journal position plus `Cargo.json`/`Market.json` fallback data to identify station/phase, distinguish partial vs full outbound loads, and avoid re-buying or replaying the wrong station's actions.
- Docking adds a configurable post-`SupercruiseExit` settle, announces the auto-docking handoff, then attempts auto-refuel plus a one-step repair follow-up before returning to station services.
- Haul departures now auto-engage hyperspace with raw key `k` after mass lock clears by default, and hyperspace arrival can auto-open the left nav panel after a configurable delay.
- Market routines now log supply/demand levels, speak low-stock warnings, reset UI focus defensively, and support targeted sells even when the station is not actively buying the carried commodity.
- `ActionDispatcher` is the single source of truth for repeated-input pacing; raw keys, repeated actions, and `submit_text` all emit separate paced taps there.
- TTS phrases now live in `defaults/tts.toml` with user overrides under `[tts]`, and `speak.py` provides a minimal direct-backend smoke test.
- Windows input injection now builds the full Win32 `INPUT` union shape and surfaces native `GetLastError()` detail on `SendInput` failures.
- CI runs the unittest suite cross-platform and enforces a 3-second full-suite ceiling; `tools/report_test_timing.py` can rank slow tests locally.

## Key Caveats

- The legacy autopilot loop is still not ported. The repo is automation/runtime tooling plus journal-driven routines, not a complete autopilot.
- Two-way hauling is the active operator path, but it still needs more live validation around startup/resume, station-role detection, and telemetry closure.
- TTS exists on macOS with Linux/Windows fallbacks, but only the macOS path should be assumed close to live-validated operator quality.
- Windows has early live validation, but it still needs broader coverage after the `INPUT` layout fix to separate residual focus/UIPI issues from backend bugs.
- CV is still in validation/scaffolding mode. Template matching has been refreshed against CrossOver captures, but there is no continuous alignment loop yet.
- Recent live-log review did not reveal a distinct journal or `Music` cue for the pre-drop "safe to disengage" moment; assume CV/vision is required if we want to trigger before `SupercruiseExit`.
- Startup binding warnings intentionally suppress unused maneuver controls (`Roll*`, `Pitch*`, `Yaw*`). Any future routine that depends on them must remove that suppression in the same change.
- The suite body is currently fast enough for the local `0.2s` target, but wrapper startup means timing checks must use the runtime reported by `uv run python3 -m unittest discover -s tests`, not generic wall-clock timing around `uv`.
- EDAP still only emulates keyboard input. Any action EDAP needs must also have a keyboard bind even if the operator normally flies with HOTAS/gamepad.

## Current Next Steps

1. Live-validate the updated two-way haul startup/resume path and haul telemetry, especially station-2 starts, station-1 run finalization, and `Market.json` fallback behavior.
2. Live-test queued TTS callouts on macOS and trim noisy phrasing, especially the low supply/demand warnings.
3. Expand Windows validation beyond the current community live check, including more `diagnostics.py --send-test-key` runs and capture of any remaining `WinError` detail.
4. Continue the next portability follow-up slice from plans 0002-0004: CV capture/performance measurement, journal latency measurement, and diagnostics/dashboard work.
5. After the next live Control Room run, verify the startup warning wording against the actual Odyssey Controls menu labels for panel and galaxy-map bindings.

## Handoff Links

- Rolling recent session notes: [session-log.md](session-log.md)
- Archive for detailed validation notes and displaced status detail: [status-archive.md](status-archive.md)
- Maintained plans: [plans/](plans/)
- Operator workflows: [operators/](operators/)
- Deeper research/history: [research/](research/) and [devlog/](devlog/)
