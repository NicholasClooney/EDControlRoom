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
- Treat the `Last updated: YYYY-MM-DD (session N)` line in `docs/STATUS.md` as the canonical session counter for the repo.
- Whenever `docs/STATUS.md` or `docs/session-log.md` is updated, increment that `session N` value exactly once for the current work session, even if only one of those two files changed.
- Keep it concise and current so the next agent can resume from it directly.
- Keep `docs/STATUS.md` bounded to at most 80 lines. If a new update would push it past the limit, move displaced older status/session detail into `docs/status-archive.md` or a more specific supporting doc, then rewrite `docs/STATUS.md` back down to a compact handoff instead of letting it grow indefinitely.
- When adding bullets to `docs/STATUS.md`, insert new bullets at the top of the relevant section so the newest handoff detail is encountered first.
- The "newest first" rule applies within each suitable section body. Do not reorder the document headers or the `Last updated` line to satisfy it.
- If `docs/STATUS.md` goes over 80 lines, trim each bullet-based status section down to its 5 newest bullets and move the older trimmed bullets into `docs/status-archive.md`.
- When archiving trimmed `docs/STATUS.md` content, prepend the newest archive block at the top of `docs/status-archive.md`.
- Do not read the whole `docs/status-archive.md` file just to prepend new archival content. Read only enough of the top of the file to insert the new block correctly, roughly `head -n 15`.
- `docs/STATUS.md` is a handoff document, not a policy document. If a working rule, architectural constraint, or style preference belongs in `AGENTS.md`, put it there once and do not restate it across `Current Snapshot`, `Active Capabilities`, or `Key Caveats`. A single short pointer in `docs/STATUS.md` (e.g. "new callback policy lives in AGENTS.md") is enough when the next session needs to know the rule exists.
- Before adding a new bullet to `docs/STATUS.md`, check whether the same idea is already present in another section in different words. If it is, update the existing bullet in place instead of adding a parallel one. Status-file duplication eats the 80-line budget without adding information.

Use [docs/session-log.md](docs/session-log.md) for concise rolling session notes.

- Append short session entries to `docs/session-log.md` when the detail is useful for future operators/agents but too transient or verbose for `docs/STATUS.md`.
- Keep `docs/session-log.md` bounded to at most 20 lines. If a new entry would push it past that limit, append the full current contents of `docs/session-log.md` to `docs/status-archive.md` and then reset `docs/session-log.md` to a fresh empty log template before writing the new entry.
- Treat `docs/status-archive.md` as cold storage for displaced older status/session content. Do not open or read it during normal work unless the user explicitly asks for archive/history detail or you are blocked and need older context that is not available in `docs/STATUS.md` or `docs/session-log.md`.

## Testing

- Use `uv run python3 -m unittest` to run tests, not pytest.
- Run a single file: `uv run python3 -m unittest tests/test_foo.py`
- Run all tests: `uv run python3 -m unittest discover -s tests`
- Do not use the bare system interpreter for test runs; the repo's `uv` environment is the required test entrypoint.
- After implementing any feature or code change, run the full suite with `uv run python3 -m unittest discover -s tests` before wrapping up.
- After implementing any feature or code change, use the runtime reported by the preceding `uv run python3 -m unittest discover -s tests` command as the timing check and keep the full-suite runtime at or under `0.2` seconds. If that command reports a runtime slower than `0.2` seconds, run `UV_CACHE_DIR=/private/tmp/uv-cache uv run python3 tools/report_test_timing.py --top 10 --sort slowest` to identify what is dragging runtime down.

### GitHub Actions Checks

- Use compact `gh` queries first so Actions debugging does not flood context.
- Recent run summary: `gh run list --limit 8 --json databaseId,workflowName,displayTitle,headBranch,event,status,conclusion,updatedAt`
- Single run job summary: `gh run view <run-id> --json databaseId,workflowName,displayTitle,headBranch,event,status,conclusion,jobs,updatedAt`
- Failed-step logs only when needed: `gh run view <run-id> --job <job-id> --log-failed`
- Default to summarizing failing jobs, failing test names, and a few key error lines. Do not pull full logs or broad JSON payloads unless the compact view is insufficient.

## Working Rules

- Keep platform-specific code isolated behind interfaces.
- Prefer explicit configuration over hardcoded paths.
- Treat macOS as the primary target until the diagnostic path is stable.
- Preserve existing OpenCV/navigation behavior unless a change is required for portability.
- Make incremental changes that are easy to validate.
- Prefer strong non-optional types when production/runtime callers always provide a value. Do not widen production APIs to `Optional[...]` just because tests want to omit an argument.
- When tests need silent progress/announcement-style hooks, pass an explicit no-op helper or lambda from the test instead of relying on `None` in the runtime signature.
- Do not give production code default no-op callback parameters. Production-facing APIs must require explicit callbacks; shared no-op callbacks are allowed only in tests or test-local wrappers/helpers.
- If you add, remove, rename, or reorder top-level `README.md` sections, update the hand-written README table of contents in the same change. GitHub exposes an automatic Outline menu, but it does not replace the inline TOC block in the file.
- When writing or updating tests, consider cross-platform behavior explicitly: avoid hardcoded path separators in expectations, and use TOML literal strings (`'...'`) for interpolated filesystem paths so Windows backslashes do not turn into invalid escapes.
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
