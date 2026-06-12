# CI and Release Status
## Current
- PR `#13` showed the expected bot-PR behavior: the promotion workflow created or updated the PR from `GITHUB_TOKEN`, so normal `pull_request` workflows did not fire on that PR even though CodeQL still produced a dynamic run on `refs/pull/13/head`.
- A repo-wide `workflow_run` notifier posts to Discord via `DISCORD_WEBHOOK_URL` whenever any workflow other than the notifier itself completes with `failure`.
- Workflow YAML changes are expected to be locally parse-validated before push so GitHub does not become the first syntax check.
- Tests run on `pull_request` and on `push` only for `main`.
- `release-please` owns release PR generation on `main`.
- `dev -> main` promotion PRs are maintained from `promote-dev-to-main--generated-iteration-archive`, rebuilt from `dev` with the generated iteration archive layered on top.
## Caveats
- Bot-authored promotion or release PRs need `PROMOTION_PR_TOKEN` or `RELEASE_PLEASE_TOKEN` if you want normal PR CI; `GITHUB_TOKEN` creation/update is fallback-only and suppresses follow-on workflow triggers.
## Next
- Live-check one intentionally failing or naturally failing Actions run to confirm the Discord payload, webhook permissions, and self-exclusion behavior.
- Live-check the promotion workflow once merged by watching branch recreation, archive refresh, and PR update behavior.
