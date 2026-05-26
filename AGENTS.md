# AGENTS

## Purpose

This repository is being refactored from a Windows-only Elite Dangerous autopilot prototype into a macOS-first project that keeps future Windows compatibility in mind.

Near-term work should optimize for:

- macOS runtime support
- Elite Dangerous running through CrossOver
- explicit user configuration for paths and hotkeys
- separation of platform-specific code from autopilot logic

## Current Direction

The immediate product goal is not a full rewrite and not a full-featured autopilot.

The macOS diagnostics checkpoint is already proven for the core runtime assumptions:

- journal access works
- bindings parsing works
- screen capture works
- synthetic input reaches the CrossOver game window

The current engineering focus is wiring parsed bindings and small runtime actions onto the new platform seams before attempting deeper autopilot behavior.

## Working Rules

- Keep platform-specific code isolated behind interfaces.
- Prefer explicit configuration over hardcoded paths.
- Treat macOS as the primary target until the diagnostic path is stable.
- Preserve existing OpenCV/navigation behavior unless a change is required for portability.
- Make incremental changes that are easy to validate.

## Agent Loop

When work is delegated to agents:

- spawn agents only for narrow, disjoint slices that can be integrated independently
- prefer concrete implementation or verification slices over broad analysis
- require the agent to verify its own work locally when practical
- require the agent to report changed files, what works, what remains unresolved, and key assumptions

After an agent finishes:

- capture the result in docs if it changes project understanding, status, or next steps
- integrate and commit the work atomically in logically grouped commits
- close the completed agent once its work has been captured

Do not leave completed agent work floating in the worktree without either committing it or intentionally discarding it.

## Commit Style

Use Conventional Commits for new commits.

Examples:

- `feat: add config loader for macOS journal path`
- `refactor: extract journal parsing from dev_autopilot`
- `docs: update README for macOS-first roadmap`
- `fix: handle missing bindings file gracefully`
