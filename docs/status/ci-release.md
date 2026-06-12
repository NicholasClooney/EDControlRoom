# CI and Release Status
## Current
- A repo-wide `workflow_run` notifier posts to Discord via `DISCORD_WEBHOOK_URL` whenever any workflow other than the notifier itself completes with `failure`.
- Tests run on `pull_request` and on `push` only for `main`.
- `release-please` owns release PR generation on `main`.
- `dev -> main` promotion PRs are maintained from `promote-dev-to-main--generated-iteration-archive`, rebuilt from `dev` with the generated iteration archive layered on top.
## Caveats
- Bot-authored promotion PRs need `PROMOTION_PR_TOKEN` or `RELEASE_PLEASE_TOKEN` if you want normal PR CI; `GITHUB_TOKEN` is fallback-only.
## Next
- Live-check one intentionally failing or naturally failing Actions run to confirm the Discord payload, webhook permissions, and self-exclusion behavior.
- Live-check the promotion workflow once merged by watching branch recreation, archive refresh, and PR update behavior.
