# Project Status

_This is the startup handoff document for the repo. Keep it current, compact, and biased toward what the next session needs immediately. Hard limit: 80 lines. If an update would push this file past the limit, move displaced older status/session detail to `docs/status-archive.md` or a more specific doc, then trim this file back down._

Last updated: 2026-06-11 (session 131)

## Current Snapshot

- GitHub-operation policy now lives in `AGENTS.md`: use `gh` commands by default for PRs, issues, Actions, releases, and other repo interactions.
- Standalone `multi_leg_haul` / `mult` now exists beside the existing two-way `haul` path: it loads either the new external EDControlRoom multi-leg JSON schema or a Spansh trade-result payload/URL, then resumes from live journal/cargo/market state instead of persisted execution state.
- The Python distribution/runtime metadata now uses `EDControlRoom` as the project name (`pyproject.toml`, `uv.lock`, version lookup constant, and Control Room update-status text), and release/update checks now point at the moved GitHub repository slug `TheClooneyCollection/EDControlRoom`.
- `release-please` is now wired for PR-based releases on `main` with the repo rooted at manifest version `1.7.3`; use a `RELEASE_PLEASE_TOKEN` secret instead of plain `GITHUB_TOKEN` if release PRs should trigger the normal CI workflows.
- PR title policy now lives in `AGENTS.md` and the GitHub PR template: use Conventional Commit-style titles for normal PRs, default `dev` -> `main` promotions to `chore: promote dev to main`, and reserve `release: ...` for versioned release PRs.
- Active docs and small user-facing CLI text now consistently say `EDControlRoom` instead of older shorthand where the project is being presented to operators.
- Active docs now use `EDControlRoom` branding for the current project name; old product-name references were removed from the maintained handoff/operator docs.
- Haul docs now describe the commander-facing value explicitly: after the drop near station, EDControlRoom handles docking request, station services, cargo trade, refuel/repair, routing, departure, mass-lock clearance, and FSD priming before handing jump alignment back to the commander via TTS.
- Routine callback policy now lives in `AGENTS.md` under Working Rules: production routine APIs require explicit progress/announcement callbacks, shared no-op helpers in `edap/routines/callbacks.py` are test-only.
- Plan 0001 (macOS MVP portability) is complete. Shared runtime, config loading, journal parsing, bindings lookup, and synthetic input are in place and live-validated on macOS + CrossOver.
- Windows now has early real-world validation from CMDR VRYAE, so the platform story is macOS-primary with initial Windows confirmation rather than macOS-only live validation.
- Current work is follow-up, not a rewrite: journal-driven routines, two-way hauling, CV/capture validation, and operator diagnostics.
- `control_room.py` is the primary operator surface. `run_routine.py`, `ship_controls.py`, `diagnostics.py`, `speak.py`, and the journal/bindings helpers remain the main manual-validation tools.

## Active Capabilities

- GitHub Actions `test_timing` now allows the full unittest suite up to `5s` in `.github/workflows/tests.yml`, matching the current CI reality while the repo still tracks local timing regressions separately with `tools/check_test_timing.py` and `tools/report_test_timing.py`.
- Operator-facing Control Room text now splits between YAML defaults: `defaults/error_messages.yaml` for paired failure `message`/`suggestion` entries and `defaults/messages.yaml` for other prompts/usage lines; `config.toml` overrides stay supported, including legacy flat error override keys.
- Control Room routine failures now surface as `Failed: ...` with operator-facing explanations plus `Try:` recovery guidance for station mismatches, destination mismatches, and commodity-name mismatches; the suggested recovery path points at replay history (`Ctrl-R` then `e`) or restarting the haul with corrected parameters instead of leaving only `Done: <step> (error)`.
- Market buy/sell routines now back out to station services before returning lookup or station-check errors that happen after the commodity market opens, so failed market selection does not leave the operator stranded inside the market UI.
- Multi-leg haul definitions now have a public copy/paste contract in `docs/schemas/multi_leg_haul.schema.json` plus `templates/multi_leg_haul.example.json`, and the normalization layer preserves Spansh route metadata separately from runtime-only phase detection.
- Control Room now accepts `multi_leg_haul <route.json | spansh-url>` with alias `mult`, records it in replay history, and runs the new standalone finite multi-leg route without modifying the existing two-way `haul` flow.
- `release-please` now patches both `pyproject.toml` and the root `EDControlRoom` package entry in `uv.lock`, so release PRs can keep repo version metadata aligned without needing a separate `uv sync` commit step.
- Market trade routines now re-center the commodity quantity dialog with `UI_Left x5` then `UI_Up x5`, giving buy/sell flows a wider safety margin when the commodity view opens off-focus.
- Journal/runtime: journal tailing, bindings lookup, runtime construction, and shared platform seams are working.
- Control Room: live Textual UI with ship status, market panel, haul stats, replay/history, persisted state, routine dispatch, queued cross-platform TTS announcements, and a repo-local `artifacts/control-room.log` journal-event mirror for sessions where the standalone watcher is not running.
- Control Room's ActivityLog now honors `control_room.activity_log_max_lines` at widget creation time, and the app layer also accepts an explicit injected override so retention can be pinned in tests or alternate launch surfaces without touching config loading.
- Control Room journal mirroring now keeps the artifact log handle buffered during steady-state event flow, flushes in small batches instead of on every event, and still forces a final flush during shutdown before closing the mirror.
- Control Room startup now writes a current-version line into `ACTIVITY`; when `control_room.check_for_updates` is enabled and GitHub confirms the local build is current it says `Currently running latest version (...)`, otherwise it logs `Currently running version ...` plus a separate newer-release notice only when GitHub reports one.
- Control Room version/update checks now read through an injectable version source so unit tests can pin fake version metadata instead of coupling assertions to the repo's live release number.

## Key Caveats

- Multi-leg haul state recovery is intentionally inference-based, not persisted: rerun the command to resume, but live validation is still needed around repeated-station routes, mixed partial cargo states, and any market layout that behaves differently across consecutive per-commodity trades.
- Current haul still has hard station-automation assumptions: docking waits for `DockingGranted` then `Docked`, and station departure waits for the post-launch `Music` `NoTrack` event as the clear-of-station cue; route setting/FSD priming do not require auto-alignment, but launch/docking still need live validation without auto launch/landing.
- Elite may hide or refuse to load a `Custom` preset when that `.binds` file includes controller mappings for a device that is not currently connected or exposed; reconnect the controller or fall back to a keyboard-only preset before treating it as a missing-file problem.
- The legacy autopilot loop is still not ported. The repo is automation/runtime tooling plus journal-driven routines, not a complete autopilot.
- Two-way hauling is the active operator path, but it still needs more live validation around startup/resume, station-role detection, and telemetry closure.
- TTS exists on macOS with Linux/Windows fallbacks, but only the macOS path should be assumed close to live-validated operator quality.
- CV is still in validation/scaffolding mode. Template matching has been refreshed against CrossOver captures, but there is no continuous alignment loop yet.

## Current Next Steps

1. Live-validate the new operator-facing failure wording in Control Room against real stale-market, wrong-station, and bad-commodity cases, and trim any messages that still sound too internal.
1. Live-validate the new market error back-out path against the real station-services/menu stack, especially after stale `Market.json` or missing-commodity failures.
1. Live-validate `multi_leg_haul` against a real Spansh result and the new external JSON schema, especially intermediate-stop resume, consecutive multi-commodity trades, and final-leg completion semantics.
1. Decide whether to keep GitHub release names manually curated to the `EDControlRoom vX.Y.Z - <short release label>` house style or add a follow-up workflow that rewrites the stock `release-please` release title after publish.
2. Live-validate the updated two-way haul startup/resume path and haul telemetry, especially station-2 starts, station-1 run finalization, and `Market.json` fallback behavior.
3. Live-test haul with auto launch/landing disabled where possible, especially whether routing still holds once `Undocked` fires and whether `Music` `NoTrack` needs a fallback clear-of-station signal.
4. Expand Windows validation beyond the current community live check, including more `diagnostics.py --send-test-key` runs and capture of any remaining `WinError` detail.
5. Continue the next portability follow-up slice from plans 0002-0004: CV capture/performance measurement, journal latency measurement, and diagnostics/dashboard work.

## Handoff Links

- Rolling recent session notes: [session-log.md](session-log.md)
- Archive for detailed validation notes and displaced older status/session detail: [status-archive.md](status-archive.md)
- Maintained plans: [plans/](plans/)
- Operator workflows: [operators/](operators/)
- Deeper research/history: [research/](research/) and [devlog/](devlog/)
