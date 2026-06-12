# Iteration Log

- Area: `ci`
- Title: `discord-workflow-failure-notify`
- Started: `2026-06-12 10:09`

## Summary

- Added a repo-level GitHub Actions failure notifier that posts failed `Tests`, `Release Please`, and `Promote Dev to Main` runs to Discord through the existing `DISCORD_WEBHOOK_URL` secret, and documented that future workflow changes must preserve and extend that notification path.

## Changes

- Added `.github/workflows/discord-workflow-failure-notify.yml`, triggered by `workflow_run`, with self-exclusion, metadata-rich payload formatting, and a no-secret skip path so forks or limited contexts do not fail on missing webhook configuration.
- Updated `AGENTS.md` with a standing GitHub Actions rule that future new or heavily rewritten workflows must keep the repo-wide Discord failure notification path intact.
- Updated `docs/status/ci-release.md` so the current CI handoff reflects the notifier and the need for a live GitHub validation run.

## Follow-ups

- Trigger or observe one failing workflow run on GitHub to verify the Discord message formatting, branch/actor metadata, and webhook delivery end to end.
