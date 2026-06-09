# Project Status

_This is the startup handoff document for the repo. Keep it current, compact, and biased toward what the next session needs immediately._

Last updated: 2026-06-09

## Current Snapshot

- Plan 0001 (macOS MVP portability) is complete. The shared runtime, config system, journal parsing, bindings lookup, and synthetic input path are in place and live-validated on macOS + CrossOver.
- The project is in follow-up work, not a full autopilot rewrite. Active work is focused on journal-driven routines, two-way hauling, CV/capture validation, and operator diagnostics.
- `control_room.py` is the primary operator surface. `run_routine.py`, `ship_controls.py`, `diagnostics.py`, and the journal/bindings helpers are the main manual-validation tools.

## Active Capabilities

- Journal/runtime: journal tailing, bindings lookup, runtime construction, and shared platform seams are working.
- Routines: `jump`, `dock`, `undock`, market buy/sell, galaxy-map destination setting, throttle zeroing, and the current two-station haul loop all exist behind `edap/routines/`.
- Two-way haul startup now detects the active station/phase from journal position, `Cargo.json`, and `Market.json` fallback data, so a station-2 start no longer blindly runs station-1 actions first.
- Two-way haul transit resume now distinguishes “already dropped near destination” from “docking already requested/granted”: it skips the extra `SupercruiseExit` wait in the first case, and waits for `Docked` instead of re-requesting docking in the second.
- Docking now waits a configurable 3-second settle after `SupercruiseExit` before the station-approach boost; `controls.dock_supercruise_exit_settle_seconds` tunes it.
- Two-way haul departures now auto-tap raw key `k` after mass lock clears to engage hyperspace FSD by default; `controls.haul_two_way_auto_hyperspace_engage` disables it when needed.
- Two-way haul transit now opens the left external panel on hyperspace arrival by default so the nav page is ready for station approach, after a configurable default 3-second delay; `controls.haul_two_way_open_nav_panel_after_hyperspace_arrival` and `controls.haul_two_way_nav_panel_open_delay_seconds` control that behavior.
- Two-way haul clear-of-station waits now default to 10 minutes; if the `NoTrack` music event still never arrives after undock, the haul aborts instead of continuing, logs a replay/`ctrl-r` recovery hint, and keeps the spoken alert short.
- Control-room haul dispatch now forwards the configured undock and clear-of-station timeouts into the two-way haul routine, so live haul progress no longer falls back to the stale `60s` `NoTrack` wait.
- Control-room haul telemetry now matches the two-way route flow: it carries the station-1 buy cost into the next clean departure, counts both station sells plus the station-2 buy, and closes a run when the return cargo is sold at station 1 instead of waiting for the next undock.
- When haul telemetry ignores a station-1 sale because tracking has not yet reached a clean departure, control room now logs that the sale profit is being discarded from the prior run instead of dropping it silently.
- Control room: live Textual UI with ship status, market panel, haul stats, replay/history, persisted state, and routine dispatch.
- Control room: live Textual UI with ship status, market panel, haul stats, replay/history, persisted state, routine dispatch, and queued cross-platform TTS announcements for haul/navigation milestones; the undock/leaving-station callout is now limited to active haul tracking instead of every `Undocked` event.
- Control-room trade parsing now accepts multi-word commodity names like `buy food cartridges` / `sell food cartridges` and still defaults them to `MAX` unless the final token is a valid explicit amount; unknown or otherwise failed commands are also persisted into replay history now.
- Control room ship status now shows `Status.json` `Destination` as `system/body/name` alongside the journal `FSDTarget`, and the background refresh cadence is configurable with `control_room.status_refresh_seconds` (default `2.0`).
- Control room startup now logs which `.binds` file it resolved and warns inline when any loaded routine action has no usable keyboard mapping, so operators can see binding gaps before dispatching routines.
- Control-room startup binding warnings now include the in-game control label and Controls-menu location for the missing action, and joystick/mouse-only binds are called out explicitly so operators know EDAP still needs a keyboard primary or secondary slot for those actions.
- Temporary exception: control-room startup currently ignores missing `RollLeftButton`, `RollRightButton`, `PitchUpButton`, `PitchDownButton`, `YawLeftButton`, and `YawRightButton` mappings because no live routine path uses those maneuver controls yet. If any future routine, CV alignment loop, or other active control-room workflow starts using any of those actions, remove them from the control-room startup ignore list immediately so missing binds become visible again at startup.
- Market buy/sell now logs station supply/demand levels, warns and speaks when the current level is critically low relative to cargo capacity, and lets operators tune that threshold with `controls.market_critical_level_multiplier`.
- Market sell still uses the original demand-sorted SELL list for cursor indexing, but if the target commodity is hidden from that list while the station still exposes a sell price, it now injects just that target row into the original order to estimate the correct position for cargo like `Food Cartridges`.
- Market sell now hard-resets the UI with `UI_Back` before entering station services, requires a current in-station journal state before it starts, and re-checks that state after backing out of the trade dialog so stale or misaligned menus fail fast instead of wandering through the UI.
- Market buy/sell now also hard-reset trade-dialog focus with `UI_Left x3` plus `UI_Up x3` immediately after opening a commodity, so quantity and confirm navigation no longer depend on the initial cursor landing on the amount controls; sell now re-holds `UI_Right` afterward based on the intended tonnage so `sell ... max` still restores the full quantity after that reset.
- `ActionDispatcher` is now the single source of truth for repeat pacing: repeated actions and raw keys are emitted as separate delayed taps there, `ShipControls` inherits that behavior without its own repeat loop, and `submit_text` now follows the same pacing semantics.
- Release prep for the next stable cut now requires `pyproject.toml` and `uv.lock` version metadata to stay in sync: bump `[project].version`, run `uv sync`, and commit the resulting lockfile change as part of the release changeset.
- Market `buy ... max` no longer holds `UI_Right` for a fixed 10 seconds: it now scales hold time from remaining cargo space with `controls.market_buy_hold_seconds_per_ton` (default `0.01s` per free ton) and still falls back to the old cap when cargo space cannot be derived.
- TTS/config: announcement IDs are typed in code, while default phrase text now lives in `defaults/tts.toml` and merges with user `config.toml` overrides under `[tts]`.
- Windows input injection now builds the full Win32 `INPUT` union shape instead of a keyboard-only subset and includes native `GetLastError()` codes in `SendInput` failures, after admin-to-admin Notepad repros suggested the old structure size could fail on 64-bit Windows before UIPI ever mattered.
- Platform scope: macOS + CrossOver is the only live-validated operator path. Windows and Linux input/runtime paths exist with unit-test and CI coverage, but not live validation.
- CI: cross-platform unittest workflow exists in GitHub Actions, a timing guard now enforces a 10-second ceiling on full unittest discovery over `tests/`, and `tools/report_test_timing.py` can rank the slowest individual unittest cases locally.

## Key Caveats

- The legacy autopilot loop is still not ported. This repo is currently automation/runtime tooling plus a growing set of journal-driven routines, not a complete autopilot.
- Two-way hauling is the active operator path, but it still needs more live validation around startup/resume/station-role detection after the latest fixes.
- TTS is implemented for macOS (`say`) plus Linux/Windows fallbacks, but only macOS is expected to be live-validated soon; wording/noise level still needs operator feedback after in-game use.
- Windows still lacks live validation; after the `INPUT` layout fix, any remaining `SendInput` failures need a fresh Windows rerun to separate residual UIPI/focus issues from backend bugs.
- CV is still at validation/scaffolding stage. Template matching has been re-baked against CrossOver captures, but there is no real continuous alignment loop yet.
- Because the control-room startup warning now suppresses currently unused maneuver bindings, any future CV/alignment or flight-control work that starts depending on roll/pitch/yaw must re-enable startup warnings for those actions in the same change.
- Timing enforcement now covers the full unittest discovery run with a 10-second budget, so CI catches both global suite regressions and single-test outliers that meaningfully move total runtime.
- Cross-platform input tests are still mostly unit-level. Hosted CI covers controller logic, binding resolution, and dispatch plumbing, but not true live desktop injection semantics for modifiers/special keys.
- EDAP still only emulates keyboard input. Players can keep HOTAS/gamepad bindings, but any action EDAP needs must also have at least one keyboard bind; joystick/mouse-only slots are treated as unavailable for automation.

## Current Next Steps

1. Live-validate the updated two-way haul startup path and haul telemetry, especially station-2 starts, station-1 run finalization, and `Market.json` fallback behavior.
2. Live-test the queued TTS callouts on macOS, including the new low supply/demand warning, and trim or reword noisy announcements based on operator feedback.
3. Keep the full-suite timing guard in place and tune the threshold only after measuring stable CI variance across several runs and platforms.
4. Re-run the Windows `diagnostics.py --send-test-key` path on a real machine and capture the new `WinError` detail if `SendInput` still fails.
5. Continue the next portability follow-up slice: CV capture/performance measurement, journal latency measurement, and diagnostics/dashboard work from plans 0002-0004.
6. Parked validation idea: add a small Python key-receiver app plus self-hosted desktop runners for end-to-end live input validation of raw keys, modifiers, and key-order semantics. Do not treat hosted CI alone as sufficient for that coverage.
7. After the next live Control Room run, verify the new startup warning wording against the actual Odyssey Controls menu labels, especially for `FocusLeftPanel` and the galaxy-map `CamZoomIn` binding.

## Handoff Links

- Rolling recent session notes: [session-log.md](session-log.md)
- Archive for detailed validation notes, longer capability status, and historical handoff detail: [status-archive.md](status-archive.md)
- Maintained plans: [plans/](plans/)
- Operator workflows: [operators/](operators/)
- Deeper research/history: [research/](research/) and [devlog/](devlog/)

## Maintenance Policy

- Keep this file high-signal only: current status, active capabilities, key caveats, immediate next steps, and minimal handoff context.
- Put short-lived session detail in [session-log.md](session-log.md). Keep that file at or under 20 lines. If a new entry would exceed the limit, append the full current log to [status-archive.md](status-archive.md), reset `session-log.md` to a fresh empty log template, then write the new entry.
- Put verbose validation logs, session chronology, long capability matrices, refactor TODOs, and speculative backlog notes in [status-archive.md](status-archive.md) or a more specific supporting doc.
- Do not read [status-archive.md](status-archive.md) during normal work unless the user explicitly asks for archive/history detail or newer compact docs are insufficient to unblock the task.
- If a section starts reading like a changelog or investigation log, move that detail out of `STATUS.md` and leave a one-line summary plus a link.
