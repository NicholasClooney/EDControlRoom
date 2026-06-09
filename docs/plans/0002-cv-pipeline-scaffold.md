# 0002: CV Pipeline Scaffold

## Status

Planned, not started.

## Why

The legacy autopilot's align loop is built on three OpenCV template matches: the compass body, the blue navpoint dot inside the compass, and the orange destination marker in the centre of the screen. The macOS port has all the plumbing around this (capture, config, geometry), but nothing has actually run `cv2.matchTemplate` against a live CrossOver Elite window on this machine.

Two questions need answers before any align / dock / undock work can land on macOS:

1. Do the legacy templates (`templates/compass.png`, `templates/navpoint.png`, `templates/destination.png`) match at acceptable scores against a real macOS + CrossOver capture, given Retina scaling and CrossOver window chrome?
2. If they do not match, what does a re-baked template need to look like at the macOS capture resolution?

This plan is intentionally scoped to answering those questions, not to porting the full align loop.

## Scope

Add a single standalone harness, `tools/scratch/scratch_cv.py`, modelled on `tools/scratch/scratch_cgevent.py`:

- Loads the shared runtime context the same way other manual scripts do (`edap.runtime.build_runtime_context`, honouring `--config`).
- Captures the configured base region once via the existing capture seam (`edap/capture.py`, `edap/platform/screen/macos.py`).
- Ports the three matching functions from legacy `archive/legacy-windows/dev_autopilot.py` as small pure functions in the script (not yet in `edap/vision.py`). Reference: `archive/legacy-windows/dev_autopilot.py:768-900` for `get_compass_image`, `get_navpoint_offset`, `get_destination_offset`.
- Runs `cv2.matchTemplate` against each template, reports the best match score, location, and the legacy threshold for comparison.
- Optionally writes an annotated debug PNG (input frame plus bounding boxes and offset markers).
- CLI surface, kept small:
  - `--config <path>` (shared)
  - `--save-debug <path>` to write the annotated frame
  - `--threshold-compass`, `--threshold-navpoint`, `--threshold-destination` to override the legacy thresholds

Out of scope:

- Continuous capture loop (covered by plan 0004's capture benchmark).
- Roll / pitch / yaw actuation based on offsets.
- Sun-brightness guard. Mention it in passing if convenient, but do not block on it.
- Promoting the matchers into `edap/vision.py`. Once the templates are validated, a follow-up can lift them out of `tools/scratch/scratch_cv.py`.

## Reference Pointers

- Legacy implementation:
  - `archive/legacy-windows/dev_autopilot.py:746-754` — `sun_percent`
  - `archive/legacy-windows/dev_autopilot.py:768-808` — `get_compass_image`
  - `archive/legacy-windows/dev_autopilot.py:810-867` — `get_navpoint_offset` (with smoothing history)
  - `archive/legacy-windows/dev_autopilot.py:869-913` — `get_destination_offset`
- Template assets: `templates/compass.png`, `templates/navpoint.png`, `templates/destination.png`.
- Capture seam: `edap/capture.py`, `edap/platform/screen/macos.py`. The capture already returns a NumPy-friendly image.
- Research note framing the question: `docs/research/0004-legacy-autopilot-port-status.md` (CV templates section).

## Acceptance Criteria

- Running `uv run python3 tools/scratch/scratch_cv.py --save-debug /tmp/cv-debug.png` against a live CrossOver Elite session prints a single block with:
  - the input capture size and the region used
  - per-template best match score, location, and pass/fail against the legacy threshold
  - the computed navpoint offset and destination offset, in pixels relative to the compass / centre
- The annotated debug image lands on disk with visible bounding boxes and offset markers, so failures are eyeballable.
- The script exits 0 if all three templates pass their thresholds, non-zero otherwise. This makes it trivially scriptable from later benchmarks.
- The script does not import anything Windows-only and does not depend on the legacy `archive/legacy-windows/dev_autopilot.py` runtime.

## Open Questions To Resolve While Building

- Does the macOS capture come back as RGB or BGR? OpenCV expects BGR; record the answer in the script's header comment so future agents do not relearn it.
- Are the legacy thresholds defined as constants somewhere, or are they inline literals? Either is fine, just be explicit when copying them.
- If templates fail to match, capture a raw frame alongside the annotated one so the user can re-bake templates without running the script again.

## Notes For The Next Agent

- This script is a probe, not a feature. Resist the urge to generalise it before we know the templates work.
- Keep it self-contained: one file, no new module under `edap/`. If it grows past ~300 lines, that is a signal to stop adding features.
- Once this lands and produces real numbers, file a follow-up either to re-bake templates or to lift the matchers into `edap/vision.py` and start a real align routine.
