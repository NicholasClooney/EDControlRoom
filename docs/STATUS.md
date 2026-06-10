# Project Status

_This is the startup handoff document for the repo. Keep it current, compact, and biased toward what the next session needs immediately. Hard limit: 80 lines. If an update would push this file past the limit, move displaced older status/session detail to `docs/status-archive.md` or a more specific doc, then trim this file back down._

Last updated: 2026-06-10 (session 115)

## Current Snapshot

- Callback API policy is now narrower than the earlier handoff note: shared no-op callbacks are allowed in tests, but production-facing routine APIs must require explicit progress/announcement callbacks and must not default to no-op helpers.
- Plan 0001 (macOS MVP portability) is complete. Shared runtime, config loading, journal parsing, bindings lookup, and synthetic input are in place and live-validated on macOS + CrossOver.
- Windows now has early real-world validation from CMDR VRYAE, so the platform story is macOS-primary with initial Windows confirmation rather than macOS-only live validation.
- Current work is follow-up, not a rewrite: journal-driven routines, two-way hauling, CV/capture validation, and operator diagnostics.
- Stable release `v1.7.3` packages bounded queued TTS/session growth, buffered Control Room journal-log flushing, injectable Control Room version metadata for tests, and the related config/test/docs coverage.
- `control_room.py` is the primary operator surface. `run_routine.py`, `ship_controls.py`, `diagnostics.py`, `speak.py`, and the journal/bindings helpers remain the main manual-validation tools.
- `bindings_files.py` now provides a quick operator utility to list `.binds` files from the detected bindings folder, copy them into the repo-local gitignored `backup/bindings/` folder, restore from numbered or interactive backup selections, and apply shipped default presets onto the active custom file after confirmation while saving a safety backup first.
- Operator-facing `bindings_files.py` usage now lives in `docs/operators/bindings-files.md`; `README.md` also notes that `apply-default` exists but still lacks live validation against a real Elite session.
- README, quickstart, and Control Room operator docs were tightened around a smaller "start here" surface: `uv sync` plus `uv run python3 control_room.py` now lead, redundant optional-config examples were removed, shortcut/focus/delay guidance is more explicit, and journal/input probe commands are framed as troubleshooting-only.
- `AGENTS.md` now explicitly requires future README section edits to keep the hand-written README TOC in sync, because GitHub's automatic Outline menu is not an inline TOC replacement.
- Windows bindings auto-detection now matches macOS/Linux by selecting the newest `.binds` file by modification time instead of the lexicographically last filename.
- Web-control UI research is now captured in `docs/research/0005-web-control-ui-options.md`, including the current NiceGUI-first prototype recommendation and the iPhone Safari LAN-HTTP caveat from NiceGUI issue `#5802`.
- Elite preset-location research is now captured in `docs/research/0006-elite-bindings-preset-locations.md`, confirming that CrossOver user bindings live under `Options/Bindings` while Frontier's built-in presets come from the installed `ControlSchemes` folder, and that controller bindings are stored as logical `Device`/`Key` tokens backed by `DeviceMappings.xml`.
- Architectural rule: prefer strong non-optional callback types when production callers always provide them; if tests need silence, pass explicit no-op callbacks instead of widening runtime APIs to `None`, and do not put no-op defaults on production routine APIs.

## Active Capabilities

- Routine callbacks: production-facing routine entrypoints now require explicit progress/announcement callbacks with no default no-op parameters, while tests may use shared no-op wrappers/helpers to keep silent call sites concise.
- Routine callbacks: progress/announcement APIs now use shared no-op helpers plus concrete non-optional callback types in the routine layer, so production entrypoints keep strong callback contracts while silent tests route through explicit no-op adapters instead of `None`.
- Journal/runtime: journal tailing, bindings lookup, runtime construction, and shared platform seams are working.
- Control Room: live Textual UI with ship status, market panel, haul stats, replay/history, persisted state, routine dispatch, queued cross-platform TTS announcements, and a repo-local `artifacts/control-room.log` journal-event mirror for sessions where the standalone watcher is not running.
- Control Room's ActivityLog now honors `control_room.activity_log_max_lines` at widget creation time, and the app layer also accepts an explicit injected override so retention can be pinned in tests or alternate launch surfaces without touching config loading.
- Control Room journal mirroring now keeps the artifact log handle buffered during steady-state event flow, flushes in small batches instead of on every event, and still forces a final flush during shutdown before closing the mirror.
- Control Room startup now writes a current-version line into `ACTIVITY`; when `control_room.check_for_updates` is enabled and GitHub confirms the local build is current it says `Currently running latest version (...)`, otherwise it logs `Currently running version ...` plus a separate newer-release notice only when GitHub reports one.
- Control Room version/update checks now read through an injectable version source so unit tests can pin fake version metadata instead of coupling assertions to the repo's live release number.
- Control Room bootstrap now restores commander name from the latest journal snapshot, so opening the UI mid-session no longer depends on catching a fresh live `LoadGame` or `Commander` event.
- Control Room and two-way haul startup now prefer the full journal-derived current station/system over stale `Market.json` metadata, and the shared ship snapshot now retains station name alongside system/status during bootstrap/resume.
- The location-regression root cause and prevention notes are captured in `docs/devlog/0002-control-room-location-regression.md`; the key lesson is that current station/system must come from one canonical journal-derived snapshot rather than ad hoc `Market.json` fallback.
- Control Room `Ctrl-C`/`Ctrl-D` handling is now haul-aware: the first interrupt during `haul` queues a stop at the next station-1 cycle boundary after the return sale, announces that deferred stop, and a second interrupt still cancels immediately.
- Routines: `jump`, `dock`, `undock`, market buy/sell, galaxy-map destination setting, and the two-way haul loop live under `edap/routines/`.
- Hauling: `edap.routines.haul_loop` now aliases the two-way implementation directly; the older one-way haul codepath is gone.
- Two-way haul resume now uses journal position plus `Cargo.json`/`Market.json` fallback data to identify station/phase, distinguish partial vs full outbound loads, and avoid re-buying or replaying the wrong station's actions.
- Docking adds a configurable post-`SupercruiseExit` settle, announces the auto-docking handoff, then attempts auto-refuel plus a one-step repair follow-up before returning to station services.
- Haul departures now auto-engage hyperspace with raw key `k` after mass lock clears by default, and hyperspace arrival can auto-open the left nav panel after a configurable delay.
- Market routines now log supply/demand levels, speak low-stock warnings, reset UI focus defensively, and support targeted sells even when the station is not actively buying the carried commodity.
- `ActionDispatcher` is the single source of truth for repeated-input pacing; raw keys, repeated actions, and `submit_text` all emit separate paced taps there.
- TTS phrases now live in `defaults/tts.toml` with user overrides under `[tts]`; `speak.py` can now smoke-test raw text or explicit `--system-name` / `--station-name` normalization; and spoken system/station names spell `3+` digit runs individually so callouts like `HIP 58412` come out as `5 8 4 1 2` while shorter tags like `B13-2` stay intact.
- Queued TTS now bounds pending backlog in-process and coalesces stale queued repeats by announcement type once speech is already in flight, so long Control Room sessions keep the latest operator-relevant callout without unbounded queue growth.
- TTS title handling now supports `tts.title_mode = "commander" | "custom" | "commander_name"`; `commander_name` uses the detected journal CMDR name once available and falls back to plain `commander` before that.
- The config loader now also accepts grouped control subtables such as `[controls.market]` and `[controls.haul.two_way]`, so `config.example.toml` can stay organized while local `config.toml` files only need the specific overrides a commander wants.
- Windows input injection now builds the full Win32 `INPUT` union shape and surfaces native `GetLastError()` detail on `SendInput` failures.
- CI runs the unittest suite cross-platform and enforces a 3-second full-suite ceiling; `tools/report_test_timing.py` can rank slow tests locally.
- Routine callback APIs should stay strongly typed in production-facing code; tests should use explicit no-op progress/announcement callbacks when silence is intentional.

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
2. Live-test the bounded/coalescing queued TTS behavior on macOS and trim noisy phrasing, especially the low supply/demand warnings.
3. Expand Windows validation beyond the current community live check, including more `diagnostics.py --send-test-key` runs and capture of any remaining `WinError` detail.
4. Continue the next portability follow-up slice from plans 0002-0004: CV capture/performance measurement, journal latency measurement, and diagnostics/dashboard work.
5. After the next live Control Room run, verify the startup warning wording against the actual Odyssey Controls menu labels for panel and galaxy-map bindings.

## Handoff Links

- Rolling recent session notes: [session-log.md](session-log.md)
- Archive for detailed validation notes and displaced older status/session detail: [status-archive.md](status-archive.md)
- Maintained plans: [plans/](plans/)
- Operator workflows: [operators/](operators/)
- Deeper research/history: [research/](research/) and [devlog/](devlog/)
