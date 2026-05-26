# Mise Python Install Findings

Date: 2026-05-26

## Scope

This note records the blocked `mise` Python provisioning investigation for this repo so it can be parked and resumed later without repeating the same experiments.

Repo state at time of testing:

- `.mise.toml` originally requested `python = "3.14"` and `uv = "latest"`
- `pyproject.toml` originally requested `requires-python = ">=3.14"`
- `mise` was installed and repo trust was already granted

## Problem

`mise install` failed for the repo's Python entry with:

```text
mise ERROR Failed to install core:python@3.14: Python installation is missing a `lib` directory
```

## What Was Tested

### 1. Pin exact Python 3.14 patch version

Command:

```sh
mise install python@3.14.5
```

Result:

- `mise` selected `cpython-3.14.5+20260510-aarch64-apple-darwin-freethreaded-install_only_stripped.tar.gz`
- install failed with the same missing `lib` directory error

### 2. Try Python 3.13 as fallback

Command:

```sh
mise install python@3.13
```

Result:

- `mise` selected `cpython-3.13.13+20260510-aarch64-apple-darwin-freethreaded-install_only_stripped.tar.gz`
- install failed with the same missing `lib` directory error

### 3. Try Python 3.12 as fallback

Command:

```sh
mise install python@3.12
```

Result:

- install succeeded
- `mise` reported that Python was installed but not activated because `.mise.toml` still points at `3.14`

## Interpretation

The suspicious part of the failing artifact path is `freethreaded`, not `stripped`.

Definitions:

- `stripped`: debug symbols removed to reduce artifact size
- `install_only`: archive contains the installed Python tree rather than a fuller build/distribution layout
- `freethreaded`: CPython build variant with the GIL removed/disabled

Key takeaways:

- `stripped` alone should not imply a missing `lib` directory
- the failure is unlikely to be caused by normal debug-symbol stripping
- the problem appears to be either:
  - a broken free-threaded standalone artifact, or
  - a `mise` selection/extraction/validation bug for free-threaded Python artifacts on this platform

The fact that `3.13` and `3.14` both selected free-threaded artifacts and both failed, while `3.12` installed successfully, suggests the issue is tied to the newer artifact path rather than to a single Python version.

## Parked Conclusion

This issue is parked for now.

Working fallback:

- Python `3.12` installs successfully with `mise` on this machine
- Repo-local toolchain was updated to `3.12` for now so `mise` + `uv` setup can proceed on this machine

Unresolved path if `3.14` is required later:

1. Try forcing a non-free-threaded precompiled flavor
2. If that fails, try compiling Python via `mise` instead of using the precompiled standalone artifact
3. If needed, inspect whether `mise` is incorrectly preferring free-threaded artifacts by default on this platform

## Suggested Next Commands For Future Follow-Up

These were identified as the next clean experiments but were not pursued further after parking the issue:

```sh
MISE_PYTHON_PRECOMPILED_FLAVOR=install_only_stripped mise install python@3.14.5
MISE_PYTHON_PRECOMPILED_FLAVOR=install_only mise install python@3.14.5
MISE_PYTHON_COMPILE=1 mise install python@3.14.5
```
