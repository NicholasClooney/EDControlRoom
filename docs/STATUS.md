# Project Status

_This is the startup handoff document for the repo. Keep it current, compact, and biased toward what the next session needs immediately. Hard limit: 80 lines. If an update would push this file past the limit, move displaced older status/session detail to `docs/status-archive.md` or a more specific doc, then trim this file back down._

Last updated: 2026-06-10 (session 116)

## Current Snapshot

- Routine callback policy now lives in `AGENTS.md` under Working Rules: production routine APIs require explicit progress/announcement callbacks, shared no-op helpers in `edap/routines/callbacks.py` are test-only.
- Plan 0001 (macOS MVP portability) is complete. Shared runtime, config loading, journal parsing, bindings lookup, and synthetic input are in place and live-validated on macOS + CrossOver.
- Windows now has early real-world validation from CMDR VRYAE, so the platform story is macOS-primary with initial Windows confirmation rather than macOS-only live validation.
- Current work is follow-up, not a rewrite: journal-driven routines, two-way hauling, CV/capture validation, and operator diagnostics.
- Stable release `v1.7.3` packages bounded queued TTS/session growth, buffered Control Room journal-log flushing, injectable Control Room version metadata for tests, and the related config/test/docs coverage.
- `control_room.py` is the primary operator surface. `run_routine.py`, `ship_controls.py`, `diagnostics.py`, `speak.py`, and the journal/bindings helpers remain the main manual-validation tools.

## Active Capabilities

- Journal/runtime: journal tailing, bindings lookup, runtime construction, and shared platform seams are working.
- Control Room: live Textual UI with ship status, market panel, haul stats, replay/history, persisted state, routine dispatch, queued cross-platform TTS announcements, and a repo-local `artifacts/control-room.log` journal-event mirror for sessions where the standalone watcher is not running.
- Control Room's ActivityLog now honors `control_room.activity_log_max_lines` at widget creation time, and the app layer also accepts an explicit injected override so retention can be pinned in tests or alternate launch surfaces without touching config loading.
- Control Room journal mirroring now keeps the artifact log handle buffered during steady-state event flow, flushes in small batches instead of on every event, and still forces a final flush during shutdown before closing the mirror.
- Control Room startup now writes a current-version line into `ACTIVITY`; when `control_room.check_for_updates` is enabled and GitHub confirms the local build is current it says `Currently running latest version (...)`, otherwise it logs `Currently running version ...` plus a separate newer-release notice only when GitHub reports one.
- Control Room version/update checks now read through an injectable version source so unit tests can pin fake version metadata instead of coupling assertions to the repo's live release number.

## Key Caveats

- The legacy autopilot loop is still not ported. The repo is automation/runtime tooling plus journal-driven routines, not a complete autopilot.
- Two-way hauling is the active operator path, but it still needs more live validation around startup/resume, station-role detection, and telemetry closure.
- TTS exists on macOS with Linux/Windows fallbacks, but only the macOS path should be assumed close to live-validated operator quality.
- Windows has early live validation, but it still needs broader coverage after the `INPUT` layout fix to separate residual focus/UIPI issues from backend bugs.
- CV is still in validation/scaffolding mode. Template matching has been refreshed against CrossOver captures, but there is no continuous alignment loop yet.

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
