# AGENTS

## Purpose

This repository is being refactored from a Windows-only Elite Dangerous autopilot prototype into a macOS-first project that keeps future Windows compatibility in mind.

Near-term work should optimize for:

- macOS runtime support
- Elite Dangerous running through CrossOver
- explicit user configuration for paths and hotkeys
- separation of platform-specific code from autopilot logic

## Current Direction

The immediate product goal is not a full rewrite and not a full-featured autopilot. The macOS MVP portability milestone is complete. Current work focuses on the follow-up plans: CV pipeline validation, journal-driven routines, and a diagnostics dashboard.

See [docs/STATUS.md](docs/STATUS.md) for the current port status, what is stubbed, what is unverified, and which plan to pick up next.

`docs/STATUS.md` is the canonical maintained-over-time status document for this repo. It is not meant to be a frozen snapshot.

- Read `docs/STATUS.md` before starting substantial work.
- Update `docs/STATUS.md` at the end of any session that changes project understanding, port status, completed work, open gaps, or recommended next steps.
- Keep it concise and current so the next agent can resume from it directly.

Use [docs/session-log.md](docs/session-log.md) for concise rolling session notes.

- Append short session entries to `docs/session-log.md` when the detail is useful for future operators/agents but too transient or verbose for `docs/STATUS.md`.
- Keep `docs/session-log.md` bounded to at most 20 lines. If a new entry would push it past that limit, append the full current contents of `docs/session-log.md` to `docs/status-archive.md` and then reset `docs/session-log.md` to a fresh empty log template before writing the new entry.
- Treat `docs/status-archive.md` as cold storage. Do not open or read it during normal work unless the user explicitly asks for archive/history detail or you are blocked and need older context that is not available in `docs/STATUS.md` or `docs/session-log.md`.

## Testing

- Use `uv run python3 -m unittest` to run tests, not pytest.
- Run a single file: `uv run python3 -m unittest tests/test_foo.py`
- Run all tests: `uv run python3 -m unittest discover -s tests`
- Do not use the bare system interpreter for test runs; the repo's `uv` environment is the required test entrypoint.
- After implementing any feature or code change, run the full suite with `uv run python3 -m unittest discover -s tests` before wrapping up.
- After implementing any feature or code change, also run the timing check and keep the full-suite runtime at or under `0.2` seconds. If the suite is slower than `0.2` seconds, run `UV_CACHE_DIR=/private/tmp/uv-cache uv run python3 tools/report_test_timing.py --top 10 --sort slowest` to identify what is dragging runtime down.

## Working Rules

- Keep platform-specific code isolated behind interfaces.
- Prefer explicit configuration over hardcoded paths.
- Treat macOS as the primary target until the diagnostic path is stable.
- Preserve existing OpenCV/navigation behavior unless a change is required for portability.
- Make incremental changes that are easy to validate.
- If implementation reveals a new runtime or behavioral assumption, verify it with the user before baking it into defaults, heuristics, or policy-level behavior.

### Manual Harness Scope

- Keep `ship_controls.py` as the human test surface for live in-game control testing.
- Add only the smallest features that materially improve manual verification loops.
- Avoid turning it into a second app, console, or long-term runtime surface.

### Manual Test Sequencing

- When generating test sequences with contradictory actions, leave time between them so the effect is observable. Examples: `SetSpeedZero -> SetSpeed100 -> SetSpeedZero`, `RollLeftButton -> RollRightButton -> RollLeftButton`.
- Prefer explicit per-step `delay=` in `ship_controls.py` sequences for this spacing.
- Never collapse repeating actions into a single repeated dispatch without delays. When an action needs to fire multiple times, send separate presses/taps with a delay between them.
- If a control helper exposes `repeat`, it must implement that as repeated single actions with built-in pacing, or the call site should be expanded into explicit separate actions instead.

## Agent Loop

When work is delegated to agents:

- spawn agents only for narrow, disjoint slices that can be integrated independently
- prefer concrete implementation or verification slices over broad analysis
- require the agent to verify its own work locally when practical
- require the agent to report changed files, what works, what remains unresolved, and key assumptions
- when two or more slices are genuinely independent and could run concurrently (different files, different concerns, no shared decisions), call that out and ask the user before spawning parallel agents — once approved, dispatch them together rather than serially

After an agent finishes:

- capture the result in `docs/STATUS.md` if it changes project understanding, status, or next steps
- capture concise operational detail in `docs/session-log.md` when it is useful to retain but does not belong in `docs/STATUS.md`
- update any deeper supporting docs only when the change needs more detail than `docs/STATUS.md` should carry
- integrate and commit the work atomically in logically grouped commits
- when bringing work back from a branch or worktree, keep history linear: prefer cherry-pick or rebase, and do not create merge commits
- close the completed agent once its work has been captured

Do not leave completed agent work floating in the worktree without either committing it or intentionally discarding it.

## Commit Style

Use Conventional Commits for new commits.

Examples:

- `feat: add config loader for macOS journal path`
- `refactor: extract journal parsing from dev_autopilot`
- `docs: update README for macOS-first roadmap`
- `fix: handle missing bindings file gracefully`

### Mixed Changesets

- If a commit/review diff mixes concerns or includes unrelated edits, tell the user before committing.
- Offer two options:

1. Detailed approach
- Separate and commit only the relevant hunks/files.

2. Rough approach
- Commit the broader tracked change set to save time/tokens.

- Default to detailed unless the user explicitly prefers speed.

## Release Style

- Tag stable releases as semantic versions like `v1.0.0`.
- When preparing a release tag, update `pyproject.toml` so `[project].version` matches the release version without the leading `v`.
- If a release prep changes `[project].version`, run `uv sync` so `uv.lock` is refreshed to the same version metadata and commit that lockfile update as part of the release-prep changeset.
- Use GitHub release titles in the form `EDAutoPilot Mk II vX.Y.Z - <short release label>`.
- Release notes should stay high level: summarize the major operator-facing capabilities, especially `control_room.py`, available routines, and any other significant platform/runtime milestones.
