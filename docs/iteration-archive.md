# Iteration Archive

_This file is generated from `docs/iteration-logs/` by `uv run python3 tools/iteration_logs.py render-archive`. Refresh it when work lands on `main` or when preparing a release, not on every feature branch._

- Legacy manual session baseline: `133`
- Generated iteration count: `10`
- Latest generated iteration number: `143`

## Iteration 134

- When: `2026-06-11 13:45`
- Area: `docs`
- Title: `status-split-and-promotion-automation`
- Source: [2026-06-11-13-45_____docs_____status-split-and-promotion-automation.md](iteration-logs/2026-06-11-13-45_____docs_____status-split-and-promotion-automation.md)

# Iteration Log

- Area: `docs`
- Title: `status-split-and-promotion-automation`
- Started: `2026-06-11 13:45`

## Summary

- Replaced the shared `docs/STATUS.md` handoff with split area status files under `docs/status/`, kept iteration logs as the chronological layer, and added a dedicated `dev -> main` promotion workflow branch that carries generated iteration-archive updates instead of pushing them directly onto `dev`.

## Changes

- Added `docs/status/README.md` plus durable area status files and per-area archive files, then removed the old top-level `docs/STATUS.md`.
- Updated `AGENTS.md`, `README.md`, `docs/README.md`, and the docs-planning references to point at the new status entrypoint and the new trimming/archive rules.
- Added `.github/workflows/promote-dev-to-main.yml` so `promote-dev-to-main--generated-iteration-archive` is rebuilt from `dev`, refreshed with the generated `docs/iteration-archive.md`, and used as the standing promotion PR head branch.

## Follow-ups

- Live-check the promotion workflow once merged by confirming the branch recreation, PR refresh, and token/CI behavior on GitHub.
- Watch a few real sessions to see whether any status area should be split further or collapsed back together.

## Iteration 135

- When: `2026-06-11 15:56`
- Area: `control-room`
- Title: `market-sell-revenue-wording`
- Source: [2026-06-11-15-56_control-room_market-sell-revenue-wording.md](iteration-logs/2026-06-11-15-56_control-room_market-sell-revenue-wording.md)

# Iteration Log

- Area: `control-room`
- Title: `market-sell-revenue-wording`
- Started: `2026-06-11 15:56`

## Summary

- Corrected the operator-facing and TTS wording for single `MarketSell` totals so Control Room reports sale revenue instead of profit.

## Changes

- Updated the Control Room market-sell announcement path and the default market-sell TTS text to say `revenue`.
- Added a regression test covering the single-sale wording while leaving haul/session profit tracking unchanged.

## Follow-ups

- Live-check the revised wording during a real station sale to make sure it still reads naturally in the operator activity stream and TTS output.

## Iteration 136

- When: `2026-06-11 16:16`
- Area: `haul`
- Title: `market-sell-indexing-and-config-cache`
- Source: [2026-06-11-16-16_____haul_____market-sell-indexing-and-config-cache.md](iteration-logs/2026-06-11-16-16_____haul_____market-sell-indexing-and-config-cache.md)

# Iteration Log

- Area: `haul`
- Title: `market-sell-indexing-and-config-cache`
- Started: `2026-06-11 16:16`

## Summary

- Fixed hidden-cargo sell-list indexing for market sales and removed repeated default-message reload overhead from Control Room routine launches.

## Changes

- Rebuilt the market sell list from the demand-sorted `Market.json` view plus the hidden-cargo subset from `Cargo.json` so hidden rows keep their correct cursor positions.
- Threaded `app._time_fn` through the Control Room routine launchers and cached default YAML message loads, cutting local full-suite runtime from `0.687s` to about `0.245s`.
- Added market-indexing and launcher/runtime regression coverage in `tests/test_routines.py`.

## Follow-ups

- Recheck the real market sell flow with multiple hidden cargo rows to confirm the corrected cursor math still matches the live station UI.

## Iteration 137

- When: `2026-06-11 18:47`
- Area: `haul`
- Title: `arrival-station-announcement`
- Source: [2026-06-11-18-47_____haul_____arrival-station-announcement.md](iteration-logs/2026-06-11-18-47_____haul_____arrival-station-announcement.md)

# Iteration Log

- Area: `haul`
- Title: `arrival-station-announcement`
- Started: `2026-06-11 18:47`

## Summary

- Moved the post-jump next-station callout into the haul transit routines so two-way and multi-leg haul announce the destination station at hyperspace arrival time.

## Changes

- Shifted the next-station TTS line out of the generic Control Room `FSDJump` announcement path and into the two haul transit flows.
- Added haul coverage for the new announcement timing in the two-way and multi-leg tests.

## Follow-ups

- Live-check the arrival callout timing against the real nav-panel open sequence to make sure the commander hears the station name before panel navigation starts.

## Iteration 138

- When: `2026-06-12 10:09`
- Area: `ci`
- Title: `discord-workflow-failure-notify`
- Source: [2026-06-12-10-09______ci______discord-workflow-failure-notify.md](iteration-logs/2026-06-12-10-09______ci______discord-workflow-failure-notify.md)

# Iteration Log

- Area: `ci`
- Title: `discord-workflow-failure-notify`
- Started: `2026-06-12 10:09`

## Summary

- Added a repo-level GitHub Actions failure notifier that posts failed `Tests`, `Release Please`, and `Promote Dev to Main` runs to Discord through the existing `DISCORD_WEBHOOK_URL` secret, then fixed the initial workflow YAML parse error and documented mandatory local workflow-YAML validation before push.

## Changes

- Added `.github/workflows/discord-workflow-failure-notify.yml`, triggered by `workflow_run`, with self-exclusion, metadata-rich payload formatting, and a no-secret skip path so forks or limited contexts do not fail on missing webhook configuration.
- Replaced the original embedded Python heredoc in the workflow with a YAML-safe one-line JSON payload builder after GitHub rejected the first draft on parse.
- Updated `AGENTS.md` with a standing GitHub Actions rule that future new or heavily rewritten workflows must keep the repo-wide Discord failure notification path intact and must locally parse-validate changed workflow YAML before push or PR update.
- Updated `docs/status/ci-release.md` so the current CI handoff reflects the notifier, the local YAML validation expectation, and the need for a live GitHub validation run.

## Follow-ups

- Trigger or observe one failing workflow run on GitHub to verify the Discord message formatting, branch/actor metadata, and webhook delivery end to end.

## Iteration 139

- When: `2026-06-12 10:09`
- Area: `docs`
- Title: `agent-worktree-requirement`
- Source: [2026-06-12-10-09_____docs_____agent-worktree-requirement.md](iteration-logs/2026-06-12-10-09_____docs_____agent-worktree-requirement.md)

# Iteration Log

- Area: `docs`
- Title: `agent-worktree-requirement`
- Started: `2026-06-12 10:09`

## Summary

- Updated the repo instructions so future delegated agents must work from their own git worktree and branch instead of sharing the main checkout.

## Changes

- Added explicit `AGENTS.md` rules for isolated agent worktrees/branches and for cleaning up agent worktrees after integration or discard.
- Updated `docs/status/docs-process.md` so the maintained docs-process handoff reflects the new delegated-agent isolation rule.

## Follow-ups

- Use the next agent-backed task to confirm the rule is practical in normal repo flow and tighten naming guidance only if friction shows up.

## Iteration 140

- When: `2026-06-12 10:18`
- Area: `docs`
- Title: `iteration-log-validation-workflow`
- Source: [2026-06-12-10-18_____docs_____iteration-log-validation-workflow.md](iteration-logs/2026-06-12-10-18_____docs_____iteration-log-validation-workflow.md)

# Iteration Log

- Area: `docs`
- Title: `iteration-log-validation-workflow`
- Started: `2026-06-12 10:18`

## Summary

- Added explicit iteration-log filename validation and documented the required `new` plus `validate` workflow in repo handoff instructions.

## Changes

- Added `validate_iteration_logs()` in `edap/iteration_logs.py` and a `validate` subcommand in `tools/iteration_logs.py`.
- Renamed the malformed `haul` iteration logs so they match the padded-area filename contract and no longer break archive generation.
- Updated `AGENTS.md`, `docs/iteration-logs/README.md`, and `docs/status/docs-process.md` to require tool-driven log creation and pre-commit/pre-PR validation.

## Follow-ups

- Consider wiring `uv run python3 tools/iteration_logs.py validate` into any future docs or PR-readiness automation so the rule is enforced mechanically.

## Iteration 141

- When: `2026-06-12 11:10`
- Area: `ci`
- Title: `pr13-workflow-root-cause-and-promotion-branch`
- Source: [2026-06-12-11-10______ci______pr13-workflow-root-cause-and-promotion-branch.md](iteration-logs/2026-06-12-11-10______ci______pr13-workflow-root-cause-and-promotion-branch.md)

# Iteration Log

- Area: `ci`
- Title: `pr13-workflow-root-cause-and-promotion-branch`
- Started: `2026-06-12 11:10`

## Summary

- Cherry-picked PR `#13`'s lone promotion-branch-only commit (`chore: update iteration archive`) onto a fresh `dev` worktree branch.
- Confirmed that the missing PR workflows were caused by the promotion PR being created or updated by Actions with `GITHUB_TOKEN`, which suppresses follow-on `pull_request` workflow triggers.
- Confirmed the `dev` vs `main` docs conflict is the legacy `docs/STATUS.md` and `docs/session-log.md` delete/modify collision from the split-status migration.

## Changes

- Added the generated iteration-archive update commit to `pr13-on-dev`.
- Updated `docs/status/ci-release.md` with the PR-13 workflow-trigger root cause and the token requirement for normal CI on bot-authored PRs.
- Updated `docs/status/docs-process.md` with the current promotion-conflict explanation and the preferred resolution direction.

## Follow-ups

- Merge the status/iteration-log migration onto `main` so future promotion PRs stop conflicting on the deleted legacy handoff files.
- If normal PR CI is desired on promotion and release PRs, create or reuse a PAT/App-backed `PROMOTION_PR_TOKEN` or `RELEASE_PLEASE_TOKEN` instead of relying on `GITHUB_TOKEN`.

## Iteration 142

- When: `2026-06-12 11:17`
- Area: `ci`
- Title: `promotion-dispatches-tests-with-github-token`
- Source: [2026-06-12-11-17______ci______promotion-dispatches-tests-with-github-token.md](iteration-logs/2026-06-12-11-17______ci______promotion-dispatches-tests-with-github-token.md)

# Iteration Log

- Area: `ci`
- Title: `promotion-dispatches-tests-with-github-token`
- Started: `2026-06-12 11:17`

## Summary

- Updated promotion verification to stay on `GITHUB_TOKEN` by dispatching the `Tests` workflow explicitly on the promotion branch after the PR is created or refreshed.

## Changes

- Added `workflow_dispatch` support to `.github/workflows/tests.yml`.
- Added `actions: write` permission and a follow-up `gh workflow run tests.yml --ref "$PROMOTION_BRANCH"` step to `.github/workflows/promote-dev-to-main.yml`.
- Updated `docs/status/ci-release.md` to document the new dispatch-based verification path and the remaining caveat for other bot-authored PRs.

## Follow-ups

- Live-check one promotion run after merge to confirm the explicit dispatch produces the expected `Tests` run on `promote-dev-to-main--generated-iteration-archive`.
- If `release-please` PRs also need automatic verification without separate credentials, add the same `workflow_dispatch` pattern there rather than relying on bot-authored `pull_request` events.

## Iteration 143

- When: `2026-06-13 16:29`
- Area: `ci`
- Title: `dev-branch-github-app-auth`
- Source: [2026-06-13-16-29______ci______dev-branch-github-app-auth.md](iteration-logs/2026-06-13-16-29______ci______dev-branch-github-app-auth.md)

# Iteration Log

- Area: `ci`
- Title: `dev-branch-github-app-auth`
- Started: `2026-06-13 16:29`

## Summary

- Moved promotion auth on `dev` from token-fallback auth to a GitHub App installation token generated from repo secrets so future promotion-branch rebuilds retain the change.

## Changes

- Added `actions/create-github-app-token` to `.github/workflows/promote-dev-to-main.yml`.
- Wired checkout, PR update, and workflow dispatch steps to use the generated app token via `BOT_APP_ID` and `BOT_APP_PRIVATE_KEY`.
- Updated `docs/status/ci-release.md` so the handoff reflects the GitHub App dependency and the live validation target.

## Follow-ups

- Merge this change into `dev`, then let the promotion workflow rebuild PR `#13` from `dev` so the branch no longer loses the app-auth patch on the next run.
- After merge, verify whether app-authenticated promotion updates produce PR-attached required checks or still only standalone branch-dispatched `Tests` runs.
