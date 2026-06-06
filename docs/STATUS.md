# Project Status

_This is the maintained status document for the repo. Update it at the end of each session when project understanding, port status, or next steps change. Keep it current over time rather than treating it as a frozen checkpoint._

Last updated: 2026-06-06 (session 9)

## Where We Are

Plan 0001 (macOS MVP portability) is complete. The four hard platform problems are proven on the current macOS + CrossOver setup:

- Journal auto-detection and parsing works against a real log.
- Bindings XML parsing and action lookup works.
- Screen capture from the CrossOver window works.
- Synthetic key input via Quartz `CGEventPost` reaches the game, including modifier combos and punctuation keys that broke the earlier `osascript` backend.

A shared runtime context, config system, bindings lookup seam, and a small runtime action surface are wired up. Utility scripts `diagnostics.py`, `ship_controls.py`, `check_bindings.py`, `set_binding.py`, `view_bindings.py`, `watch_journal.py`, and `run_routine.py` all work.

The first journal-driven runtime pieces now exist:

- `JournalWatcher` tails the latest `Journal.*` file incrementally, starts at end-of-file by default, and rolls over to newer journal files.
- `auto_zero_throttle_on_arrival` exists as the first watcher-to-controls routine and dispatches `SetSpeedZero` on `SupercruiseExit`.
- `jump` now exists as the first retrying journal-driven routine. It dispatches `HyperSuperCombination`, waits for `StartJump` / hyperspace start, then waits to re-enter `in_supercruise` and zeroes throttle.
- `dock` now exists as a journal-driven station approach routine. It can wait for `SupercruiseExit`, send the legacy docking-request menu walk, wait for docking journal events, and optionally chain the in-station refuel menu.
- `undock` now exists as a journal-driven routine. It sends `UI_Back x10`, `HeadLookReset`, a single `UI_Down` tap, and `UI_Select` to trigger launch, then polls for the `Undocked` journal event (configurable timeout, default 30s). The legacy `SetSpeedZero` calls between launch confirm and undock completion were dropped — the ship is still in the docking bay at that point and throttle state is irrelevant. Discrepancy noted in `docs/plans/0003-journal-driven-routines.md`.
- `run_routine.py` now supports `auto_zero_throttle_on_arrival`, `jump`, `dock`, `station_refuel_menu`, and `undock` as live manual harnesses for exercising journal-driven paths against a real Elite session.
- `run_routine.py` now emits live progress to stderr (waiting-for-event, event-detected, key-presses, pauses). JSON output is opt-in via `--json`.
- The current live manual test flows for those harnesses are documented in `docs/manual-journal-routine-testing.md`.

Latest live validation on the current macOS + CrossOver setup:

- raw key injection through `diagnostics.py --send-test-key` was re-validated after restoring macOS Accessibility permission for the terminal app
- `watch_journal.py` confirmed live journal tailing and the expected event vocabulary
- `run_routine.py --routine jump --log-events` captured the expected hyperspace sequence: `StartJump` with `JumpType == "Hyperspace"` followed by `FSDJump`
- `run_routine.py --routine dock --skip-supercruise-exit --auto-refuel --log-events` completed a full dock-and-refuel cycle; live testing revealed a retry-after-grant bug (watcher offset primed too late when supercruise wait is skipped) which was fixed in `edap/routines.py`
- Dock routine was further extended (not yet live-validated): boost after SupercruiseExit with configurable settle time, DockingDenied retry loop with configurable delay, `ui_left` after `ui_select` to dismiss the station contact menu
- `run_routine.py --routine undock --log-events` completed a full undock cycle from a docked state
- `run_routine.py --routine set_gal_map_destination --destination "Colonia" --delay-seconds 5` live-validated: two input bugs found and fixed — modifier key was not explicitly pressed/released (caused ctrl bleed-through to subsequent keys), and `type_text` used keycode 0 for every character (CrossOver ignores the unicode string and reads the physical keycode, so all text arrived as AAAA...); both fixed in `edap/platform/input/macos.py`

The important caveat is that the real autopilot loop is still largely unported. The project is in a portability-first and runtime-seams phase, not a "macOS autopilot feature complete" phase.

## Port Status

| Capability | Status | Notes |
| --- | --- | --- |
| Journal parsing | Done | `edap/state.py` — tested against real journals |
| Bindings XML parsing | Done | `edap/bindings.py`, `edap/binding_lookup.py` |
| Action dispatch | Done | `edap/actions.py`, `edap/ship_controls.py` — 0.1s dwell floor, 0.2s continuous default |
| macOS input backend | Done | `edap/platform/input/macos.py` — Quartz CGEvent, modifier combos work; modifier key is now explicitly pressed/released to prevent flag bleed-through to subsequent keypresses |
| Screen capture (one-shot) | Done | `edap/platform/screen/macos.py`, `edap/capture.py` — normalized regions |
| Config loading | Done | `edap/config.py`, `config.example.toml` |
| Runtime context assembly | Done | `edap/runtime.py` — config fallback, path resolution, optional binding lookup, platform adapter wiring |
| CV pipeline (compass, navpoint, destination) | Not ported | No template matching in `edap/` yet — blocked on plan 0002 |
| Align loop | Not ported | Depends on CV pipeline |
| Journal watcher | Done | `edap/state.py` — incremental tailing with rollover support and tests |
| Auto-zero throttle on arrival | Done | `edap/routines.py` — dispatches `SetSpeedZero` on `SupercruiseExit` |
| Jump sequencing | Done | `edap/routines.py` — retrying journal-driven routine with start/completion timeouts and throttle-zero follow-up |
| Refuel sequencing | Deferred | Legacy behavior is understood, but implementation is intentionally paused for now |
| Dock sequencing | Done | `edap/routines.py` — waits on journal events, boosts after SCX and settles, drives legacy-style docking request UI walk (with `ui_left` to exit contacts menu), retries after DockingDenied with configurable delay, optionally chains station refuel menu |
| Undock sequencing | Done | `edap/routines.py` — menu walk (UI_Back x10, HeadLookReset, UI_Down, UI_Select), polls for `Undocked` event; live-validated |
| Station / docked state detection | Partial | `edap/state.py` derives coarse statuses like `in_station`, `starting_docking`, and `in_docking`, but there is no dedicated docked/station snapshot model yet |
| Hotkey registration | Parked | `keyboard` lib doesn't work on macOS; likely future direction is a menu-bar app |
| Legacy autopilot loop migration | Not ported | `dev_autopilot.py` remains the behavior reference; new `edap/` routines are still minimal |
| Market data reading | Done | `scratch_market.py` — reads `Market.json` from journal dir, mirrors in-game layout (alphabetical categories, alphabetical items within each); `--raw` flat table with sort options |
| Market buy/sell routine | Done (not live-validated) | `edap/routines.py` — `market_buy` / `market_sell` wired to `run_routine.py`; sell list filtered by `DemandBracket > 0` (matches game); sell skips quantity input (game pre-fills full cargo); `UI_Back x2` after trade to return to station menu; station guard with `--skip-station-check` bypass; `--target` / `--amount` / `--step-delay-seconds` flags |
| Community haul loop | **Needs live validation** | `edap/routines.py` — `haul_loop` chains existing pieces: sell all cargo from `Cargo.json` (skips stolen/mission), undock, wait SCX + dock at buy station, buy MAX commodity, undock, wait SCX + dock at sell station with auto-refuel, repeat; wired to `run_routine.py` as `--routine haul_loop --target <commodity> [--buy-station NAME] [--sell-station NAME] [--iterations N]` (0 = infinite) |
| Galaxy map destination | **Bug: Z lands in search bar** | `edap/routines.py` — restored original sequence: UI_Right + UI_Select (pick result), CamZoomIn/Z + UI_Select held 0.75s (plot), NavRoute.json polled up to `plot_timeout_s` (default 15s) instead of fixed sleep, retries through up to `max_results` (default 5) on mismatch; `--plot-timeout-seconds` flag in `run_routine.py`; Bug: CamZoomIn (Z) reaches the search field while it is still in text-input mode — fix pending |
| Control room TUI | **Needs live validation** | `control_room.py` — Textual TUI with ship status, activity log, and market panels; dispatches `dock`/`undock`/`jump`/`buy`/`sell`/`haul`/`dest` routines from the input bar; `dest <system>` / `set_dest <system>` wired to `set_gal_map_destination`; `sell` with no args iterates full cargo manifest; `haul [commodity]` prompts step-by-step for commodity, buy station, sell station; sell station defaults to current docked station; enforces start-at-sell-station precondition; `verbose on/off` toggles key press logging; command history (up/down arrows); Ctrl-C/Ctrl-D require double-press to exit (5s window); input bar auto-focused on launch; `market filter <name>` sets filter (title-cased); `market` / `market clear` clears; `market lock/unlock` |

## Unverified on macOS / CrossOver

- **CV templates on Retina + CrossOver.** All three templates re-baked and passing against live CrossOver captures: compass (re-baked from equalized region), navpoint (was already passing), destination (re-baked from orange-filtered center region; `_filter_orange2` range loosened from `[15,220,220]–[30,255,255]` to `[10,100,80]–[30,255,255]` to match CrossOver rendering). `scratch_rebake.py` added as a helper for future re-bakes. Scores observed: compass ~0.6+, navpoint ~0.86, destination passing when target reticle is centered on screen.
- **Real-time capture loop.** Only ever captured a single frame. Frame rate and capture cost in a continuous loop are unmeasured.
- **Journal write latency vs poll rate.** We have not measured how quickly Elite (through CrossOver) flushes events to disk relative to a 0.5s poll.
- **Window focus during autopilot.** `CGEventPost` is global on macOS; behavior across focus loss and multi-monitor setups during a live run is untested.

Full detail: `docs/research/0004-legacy-autopilot-port-status.md`.

## Next Plans

| Plan | File | Depends on | Ready to start |
| --- | --- | --- | --- |
| 0002 CV Pipeline Scaffold | `docs/plans/0002-cv-pipeline-scaffold.md` | nothing | yes |
| 0003 Journal-Driven Routines | `docs/plans/0003-journal-driven-routines.md` | nothing | yes |
| 0004 Runtime Diagnostics Dashboard | `docs/plans/0004-runtime-diagnostics-dashboard.md` | 0002/0003 helpful first | after |
| 0005 Market Trading Routine | `docs/plans/0005-market-trading-routine.md` | 0003 (JournalWatcher) | gated on 3 open questions |

Plans 0002 and 0003 are independent and can run in parallel.

## Ideas / Future Work

These are not scheduled yet but worth capturing for planning.

- **Galaxy map input.** Implemented as `set_gal_map_destination` in `edap/routines.py`. Live validation pending: OCR-based open detection (`open_check_fn`) is optional; defaults to a settle delay. Wired into `control_room.py` as `dest <system>` / `set_dest <system>`.
- **Market trading.** Journal events alone do not contain commodity listings. Elite Dangerous writes a `Market.json` file to the journal directory whenever the player opens the commodities market screen in-game. It contains the full listing per station: commodity name, buy/sell price, stock units, stock bracket (0-3), demand, and category. `MarketBuy`/`MarketSell` events are written to the journal on completed trades. The market tracker should watch for `Docked` events (station identity) and read `Market.json` (written when market screen opens) to snapshot each station's inventory. From there, UI automation can drive buy/sell sequences using Market.json item order + count-based navigation, since there is no CV yet to read the screen.
- **SC Assist speed management and disengage.** The 7-second rule is the core supercruise disengage mechanic: throttle back when ETA hits ~7s or you overshoot the target. Primary signal is OCR of the ETA countdown next to the destination reticle (small dynamic number, needs pytesseract on an orange-filtered crop). The "TO DISENGAGE" popup is a useful secondary/fallback trigger — it confirms the safe window is open and should still be detected even if ETA OCR misses. Broader throttle strategy: boost out of the departure star's gravity well early, then coast and bleed speed well before the target; how much depends on the remaining distance. Gravity wells from large bodies mid-route can pull the ship off line and slow it — this is pure in-engine physics with no journal signal, so it can only be detected by watching the alignment drift or ETA stalling.
- **Human-like input variation.** Add randomized dwell and inter-key delay variation to all synthetic input so sequences look less robotic. For menu-heavy flows (market buy/sell), include occasional overshoot-and-correct behavior (navigate past item, back up) to mimic human selection patterns.
- **Monitoring and command center CLI.** Implemented in `control_room.py` (Textual TUI, `textual>=0.60` added to `pyproject.toml`). Three panels: SHIP STATUS (commander, system, station, flight status, fuel bar, credits, cargo fill, FSD target — bootstrapped from journal on startup, updated live), ACTIVITY (timestamped one-liners for jumps, docks, trades, missions, refuels — historical events suppressed), MARKET (current station from `Market.json`, auto-reloads on mtime change). Routine dispatch from the input bar: `dock`, `undock`, `jump`, `buy <item> [N]`, `sell`, `sell <item> [N]`, `haul [commodity]`, `dest <system>` / `set_dest <system>`. Market filter: `market filter <name>` (title-cased); `market` / `market clear` clears; `market lock/unlock`. Command history via up/down arrows. Ctrl-C/Ctrl-D double-press to exit. Input auto-focused on launch. Haul sell station defaults to current docked station. Not yet live-validated.

- Next task in 0003: `undock` is live-validated. `refuel` is the only remaining routine; it remains intentionally deferred.
- `refuel` is intentionally deferred for now.
- Next task for 0005: live-validate `market_buy` and `market_sell`. Navigation count bug fixed (sell list was using `Demand > 0`; corrected to `DemandBracket > 0`). First full test: `--routine market_sell --target Aluminium --amount MAX --step-delay-seconds 1 --delay-seconds 5`. Once market_buy/sell are validated, validate `haul_loop` end-to-end: `--routine haul_loop --target Aluminium --sell-station "Jameson Memorial" --buy-station "Hutton Orbital" --delay-seconds 10`.
- Next task in 0002: CV templates are validated. Next step is plan 0004 — measure capture-loop performance and journal latency, then wire CV into a real alignment loop.
- **TODO `scratch_telemetry.py`**: continuous screen monitor that reads and prints speed, distance, and ETA on a single updating line. Two OCR sources: left panel (fixed position — `SPEED xx.xkm/s`, `DISTANCE xx.xMm`) and reticle label (floats with destination circle — `xx.xMm` / `m:ss`). Pipeline: crop region → orange filter → 3x scale-up → pytesseract with digit/unit whitelist. Requires `pytesseract` in `pyproject.toml` and `brew install tesseract`. Left panel fixed crop is lowest-risk starting point; reticle label position can be derived from the destination template match result. Target loop rate ~1Hz.
