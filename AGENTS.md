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

See [docs/status/README.md](docs/status/README.md) for the maintained status entrypoint, current area breakdown, and which area files to read before resuming work.

`docs/status/*.md` are the canonical maintained current-state handoff documents for this repo. They are not frozen snapshots and they are not rolling logs.

- Read `docs/status/README.md` plus the relevant `docs/status/<area>.md` files before starting substantial work.
- Update only the affected `docs/status/<area>.md` files at the end of any session that changes project understanding, port status, completed work, open gaps, or recommended next steps for that area.
- Keep each `docs/status/<area>.md` concise, current, and bounded to at most 20 lines so the next agent can resume from it directly.
- Each status file should contain only high-value current truth: active capabilities, key caveats, and next steps for that area. Iteration logs hold chronology and detail.
- When adding bullets to `docs/status/<area>.md`, insert new bullets at the top of the relevant section so the newest current handoff detail is encountered first.
- Before adding a new bullet to an area status file, check whether the same idea is already present in different words. If it is, update the existing bullet in place instead of adding a parallel one.
- If a `docs/status/<area>.md` file would exceed 20 lines, first compress or replace older bullets that no longer reflect the latest truth. If it still does not fit, move the displaced older bullets into `docs/status/archive/<area>.md`.
- When archiving trimmed status content, prepend the newest archive block at the top of `docs/status/archive/<area>.md`.
- Do not read the whole `docs/status/archive/<area>.md` file just to prepend a new block. Read only enough of the top of the file to insert the new archive block correctly.
- `docs/status/*.md` are handoff documents, not policy documents. If a working rule, architectural constraint, or style preference belongs in `AGENTS.md`, put it there once and keep the area status files focused on current repo truth.

Use [docs/iteration-logs/](docs/iteration-logs/) for concise per-iteration notes.

- Create one iteration log file for each substantive work session that changes project understanding, status, code, docs workflow, or recommended next steps.
- Name each file `YYYY-MM-DD-HH-MM_<area>_<title>.md`.
- `_` separates fields; `-` separates words inside each field.
- `<area>` is a short kebab-case slug center-padded with underscores to width `12` so `control-room` fits exactly. Example: `2026-06-11-13-45_____docs_____iteration-log-migration.md`.
- Do not hand-edit an iteration number anywhere; derive it from `docs/iteration-logs/` with `uv run python3 tools/iteration_logs.py next-number` or the generated archive.
- `docs/iteration-archive.md` is generated from `docs/iteration-logs/`. Prefer the dedicated promotion workflow branch to refresh it for `dev -> main` PRs, and refresh it manually only when needed for local verification or release prep.
- Treat `docs/status-archive.md` as legacy cold storage for displaced older status/session content from the pre-iteration-log and pre-area-status workflows. Do not open or read it during normal work unless the user explicitly asks for archive/history detail or you are blocked and need older context that is not available in `docs/status/` or `docs/iteration-logs/`.

## Testing

- Use `uv run python3 -m unittest` to run tests, not pytest.
- Run a single file: `uv run python3 -m unittest tests/test_foo.py`
- Run all tests: `uv run python3 -m unittest discover -s tests`
- Do not use the bare system interpreter for test runs; the repo's `uv` environment is the required test entrypoint.
- After implementing any feature or code change, run the full suite with `uv run python3 -m unittest discover -s tests` before wrapping up.
- After implementing any feature or code change, use the runtime reported by the preceding `uv run python3 -m unittest discover -s tests` command as the timing check and keep the full-suite runtime at or under `0.2` seconds. If that command reports a runtime slower than `0.2` seconds, run `UV_CACHE_DIR=/private/tmp/uv-cache uv run python3 tools/report_test_timing.py --top 10 --sort slowest` to identify what is dragging runtime down.

### GitHub Actions Checks

- When operating on GitHub for this repo, use `gh` commands by default for PRs, issues, Actions, releases, and other repo interactions rather than browser/manual UI flows.
- Use compact `gh` queries first so Actions debugging does not flood context.
- Recent run summary: `gh run list --limit 8 --json databaseId,workflowName,displayTitle,headBranch,event,status,conclusion,updatedAt`
- Single run job summary: `gh run view <run-id> --json databaseId,workflowName,displayTitle,headBranch,event,status,conclusion,jobs,updatedAt`
- Failed-step logs only when needed: `gh run view <run-id> --job <job-id> --log-failed`
- Default to summarizing failing jobs, failing test names, and a few key error lines. Do not pull full logs or broad JSON payloads unless the compact view is insufficient.
- Keep Discord failure notifications enabled for GitHub Actions. New or substantially rewritten workflows must continue to trigger the repo-wide `DISCORD_WEBHOOK_URL` failure notification path instead of bypassing or replacing it silently.

## Working Rules

- Keep platform-specific code isolated behind interfaces.
- Prefer explicit configuration over hardcoded paths.
- Treat macOS as the primary target until the diagnostic path is stable.
- Preserve existing OpenCV/navigation behavior unless a change is required for portability.
- Make incremental changes that are easy to validate.
- Never use `git reset --hard` as a first option. Always consider safer alternatives first, and if a hard reset truly seems necessary, consult the user before doing it.
- Prefer strong non-optional types when production/runtime callers always provide a value. Do not widen production APIs to `Optional[...]` just because tests want to omit an argument.
- When tests need silent progress/announcement-style hooks, pass an explicit no-op helper or lambda from the test instead of relying on `None` in the runtime signature.
- Do not give production code default no-op callback parameters. Production-facing APIs must require explicit callbacks; shared no-op callbacks are allowed only in tests or test-local wrappers/helpers.
- Prefer semantic Elite action dispatch through bindings lookup very strongly over direct raw key input. Use raw key injection only when there is no viable semantic action path, keep that exception narrowly scoped, and confirm the runtime assumption with the user before baking a raw key into production behavior.
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

- start each agent in its own git worktree on its own branch; do not let multiple agents share the main checkout or a branch
- name the branch and worktree for the slice they own so the result is easy to inspect, test, and clean up
- spawn agents only for narrow, disjoint slices that can be integrated independently
- prefer concrete implementation or verification slices over broad analysis
- require the agent to verify its own work locally when practical
- require the agent to report changed files, what works, what remains unresolved, and key assumptions
- when two or more slices are genuinely independent and could run concurrently (different files, different concerns, no shared decisions), call that out and ask the user before spawning parallel agents — once approved, dispatch them together rather than serially

After an agent finishes:

- capture the result in the affected `docs/status/<area>.md` files if it changes project understanding, status, or next steps
- capture concise operational detail in a new file under `docs/iteration-logs/` when it is useful to retain but does not belong in `docs/status/<area>.md`
- update any deeper supporting docs only when the change needs more detail than the relevant `docs/status/<area>.md` file should carry
- integrate and commit the work atomically in logically grouped commits
- remove the agent worktree after its changes are integrated or intentionally discarded so stale checkouts do not accumulate
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

## PR Title Style

- Use Conventional Commit style for pull request titles too: `feat: ...`, `fix: ...`, `refactor: ...`, `docs: ...`, `chore: ...`.
- PR titles should describe the net effect of the PR, not enumerate every commit inside it.
- If a PR mixes unrelated work, split it instead of stacking multiple type prefixes into one title.
- For normal feature/fix/refactor/docs PRs, use the matching Conventional Commit type in the PR title.
- For branch-promotion PRs from `dev` to `main`, default to `chore: promote dev to main`.
- Reserve `release: ...` titles for versioned release PRs only when the branch is promoting a specific release.

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
- Use GitHub release titles in the form `EDControlRoom vX.Y.Z - <short release label>`.
- Release notes should stay high level: summarize the major operator-facing capabilities, especially `control_room.py`, available routines, and any other significant platform/runtime milestones.
