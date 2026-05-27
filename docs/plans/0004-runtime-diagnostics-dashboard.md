# 0004: Runtime Diagnostics Dashboard

## Status

Planned, not started.

## Why

Research note 0004 (`docs/research/0004-legacy-autopilot-port-status.md`, Future Test Items) flagged three measurement gaps on macOS + CrossOver that no one has actually probed:

- How fast can we capture the configured screen region in a tight loop?
- How quickly does Elite (through CrossOver) flush a journal event to disk after the in-game effect is visible?
- When a routine feels laggy or wrong, can we see at a glance whether capture, journal, or input dispatch is the cause?

These are pre-requisites for both the CV scaffold (plan 0002) and the journal-driven routines (plan 0003). Without numbers we are guessing at poll intervals and frame rates.

The end state is a single `rich.live`-driven dashboard, modelled on YouTube's "stats for nerds" overlay, that runs alongside any routine or on its own.

## Scope

Three deliverables, each useful on its own and combinable into the final dashboard.

### 1. Capture-loop benchmark

Small script (`scratch_capture_bench.py` or an extension of `diagnostics.py`) that captures the configured base region in a tight loop for N seconds against a live CrossOver Elite window. Reports:

- frame count and elapsed seconds
- mean and p99 frame time
- whether the window position drifted during the run (compare first vs. last capture geometry if accessible)

CLI:

- `--config <path>`
- `--duration-s <seconds>` (default 5)
- `--region <name>` to pick a named subregion if useful

Acceptance: produces plain numbers so a human can sanity-check that a 10 Hz align loop is feasible without saturating CPU.

### 2. Journal write-latency probe

Small script (`scratch_journal_latency.py`) that runs alongside a live Elite session and times the gap between a user action and the journal line that records it.

Approach:

- Take a baseline file offset on the latest `Journal.*`.
- Prompt the user to perform a specific action (`FSDJump`, `SupercruiseExit`, `Docked`, `Undocked`) and press Enter when the in-game effect completes.
- Poll the journal until the corresponding event line appears, record the delta.
- Repeat across a small menu of events, output a histogram (or just min / mean / p99 per event type).

Acceptance: produces a measured floor for journal poll intervals so plan 0003's `JournalWatcher` has a real default rather than a guess.

### 3. "Stats for nerds" dashboard

Single `rich.live`-driven view (`stats.py` in the repo root) that runs alongside any routine or on its own. Layout suggestion (refine when building):

- Top row: capture FPS, last capture latency, configured region
- Middle row: last journal event, time since last event, current `ShipState` summary
- Lower row: action dispatch history (last N actions), hotkey state (when hotkeys exist)
- Footer: warnings (e.g. journal stale > 5s, capture dropped frames)

CLI:

- `--config <path>`
- `--no-capture` to skip the capture loop if the user only wants journal + dispatch view
- `--routine <name>` (optional) to launch a routine from plan 0003 inside the same process so the dashboard reflects its dispatches

Acceptance: a single glance during a live session tells the user whether capture, journal, or input is the cause of perceived lag.

## Reference Pointers

- Source of the test items: `docs/research/0004-legacy-autopilot-port-status.md` (Future Test Items section).
- Capture seam: `edap/capture.py`, `edap/platform/screen/macos.py`.
- Journal seam: `edap/state.py`. Plan 0003's `JournalWatcher` is the right abstraction for the dashboard once it exists; until then, poll directly.
- `rich.live`, `rich.table`, `rich.panel` are already used in `view_bindings.py` — same style.
- Dispatcher: `edap/actions.py:ActionDispatcher`. The dashboard can hook a dispatch history by wrapping the dispatcher or by recording results from `ShipControls`.

## Acceptance Criteria

- `scratch_capture_bench.py` produces a one-screen report with frame count, mean frame time, p99 frame time, and a drift flag.
- `scratch_journal_latency.py` produces per-event-type latency stats across at least three event types in a single live session.
- `stats.py` renders a live dashboard at no less than 5 Hz refresh, runs against a live Elite session, and degrades gracefully when capture or journal is unavailable (e.g. ED not running).
- The three scripts share the same `edap.runtime.build_runtime_context` entry point so they reuse the existing config plumbing.

## Open Questions To Resolve While Building

- Does the capture cost on this machine include a per-call permission check, or is the first capture the only slow one? The benchmark will surface this.
- Is the `rich.live` refresh rate the right knob for the dashboard, or do we want per-panel update cadences (capture fast, journal slower)? Start simple, split later if needed.
- How should the dashboard surface input dispatch — by hooking `ActionDispatcher`, by reading a shared queue, or by polling a `ShipControls` wrapper? Decide once routines exist.

## Notes For The Next Agent

- Build deliverables 1 and 2 first — they answer real questions. The dashboard only makes sense once those measurements are flowing.
- This whole plan can be deferred if plan 0003's routines uncover a different, more painful debugging gap. Re-evaluate after the first journal routine lands.
- Resist building a configuration UI inside the dashboard. It is read-only telemetry; keep it that way.
