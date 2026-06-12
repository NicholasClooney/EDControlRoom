# Docs Process Status
## Current
- `main` still carries the legacy `docs/STATUS.md` and `docs/session-log.md`, so `dev -> main` promotion currently hits delete/modify conflicts there until the split-status migration lands on `main`.
- Iteration logs should now be created with `uv run python3 tools/iteration_logs.py new "<area>" "<title>"` and validated with `uv run python3 tools/iteration_logs.py validate` before commits, pushes, and PRs so malformed filenames do not break archive generation.
- Delegated-agent workflow now requires one branch and one git worktree per agent slice so concurrent work stays isolated from the main checkout.
- Maintained current-state handoff now lives in `docs/status/*.md` instead of a single shared `docs/STATUS.md`.
- Per-iteration notes live in `docs/iteration-logs/`, and `docs/iteration-archive.md` is generated rather than manually maintained.
- Legacy global handoff history remains in `docs/status-archive.md`; new displaced area-status history belongs in `docs/status/archive/*.md`.
## Caveats
- Archive generation still depends on every iteration log matching the exact filename contract, so malformed manual renames remain a hard failure until validation is run.
- Until `main` absorbs the split-status migration, promotion conflict resolution must intentionally prefer the new `docs/status/*` and `docs/iteration-logs/*` structure over reviving the deleted legacy files.
## Next
- Fold `uv run python3 tools/iteration_logs.py validate` into any future automation that gates PR readiness or release-prep docs checks.
- Merge the split-status migration through to `main`, then remove the temporary promotion-conflict handling burden around the legacy handoff files.
- Trim or merge area files aggressively if any start drifting toward branch-by-branch narrative instead of current truth.
