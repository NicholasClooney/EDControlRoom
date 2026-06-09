"""
CV pipeline probe for Elite Dangerous macOS + CrossOver.

Captures one frame via the configured screen region, runs the three legacy
template matchers (compass, navpoint, destination), and reports scores vs.
the legacy thresholds.

Color note: PIL.ImageGrab.grab() returns RGB. OpenCV expects BGR. The
conversion is applied once after capture (RGB→BGR). All cv2 operations
below work on BGR arrays.

Usage:
    uv run python3 tools/scratch/scratch_cv.py
    uv run python3 tools/scratch/scratch_cv.py --save-debug /tmp/cv-debug.png
    uv run python3 tools/scratch/scratch_cv.py --save-debug /tmp/cv-debug.png --save-raw /tmp/cv-raw.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from edap.capture import PixelBounds, build_capture_layout
from edap.runtime import build_runtime_context, load_config_with_fallback

_THRESHOLD_COMPASS = 0.3
_THRESHOLD_NAVPOINT = 0.5
_THRESHOLD_DESTINATION = 0.2


def _equalize(bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _filter_blue(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 100, 255]))


def _filter_orange2(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, np.array([10, 100, 80]), np.array([30, 255, 255]))


def _match_compass(
    region: np.ndarray, template_path: Path, threshold: float
) -> tuple[float, tuple[int, int], bool, tuple[int, int]]:
    tmpl = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if tmpl is None:
        raise FileNotFoundError(f"template not found: {template_path}")
    th, tw = tmpl.shape[:2]
    result = cv2.matchTemplate(_equalize(region), tmpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    return score, loc, score >= threshold, (tw, th)


def _match_navpoint(
    compass_region: np.ndarray, template_path: Path, threshold: float
) -> tuple[float, tuple[int, int], bool, tuple[int, int], dict[str, float] | None]:
    tmpl = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if tmpl is None:
        raise FileNotFoundError(f"template not found: {template_path}")
    th, tw = tmpl.shape[:2]
    rh, rw = compass_region.shape[:2]
    result = cv2.matchTemplate(_filter_blue(compass_region), tmpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    passed = score >= threshold
    offset = None
    if passed:
        offset = {
            "x": (loc[0] + 0.5 * tw) - (0.5 * rw),
            "y": (0.5 * rh) - (loc[1] + 0.5 * th),
        }
    return score, loc, passed, (tw, th), offset


def _match_destination(
    center_region: np.ndarray, template_path: Path, threshold: float
) -> tuple[float, tuple[int, int], bool, tuple[int, int], dict[str, float] | None]:
    tmpl = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if tmpl is None:
        raise FileNotFoundError(f"template not found: {template_path}")
    th, tw = tmpl.shape[:2]
    rh, rw = center_region.shape[:2]
    result = cv2.matchTemplate(_filter_orange2(center_region), tmpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    passed = score >= threshold
    offset = None
    if passed:
        offset = {
            "x": (loc[0] + 0.5 * tw) - (0.5 * rw),
            "y": (0.5 * rh) - (loc[1] + 0.5 * th),
        }
    return score, loc, passed, (tw, th), offset


def _save_debug(
    frame_bgr: np.ndarray,
    compass_b: PixelBounds,
    center_b: PixelBounds,
    compass_res: tuple,
    navpoint_res: tuple,
    destination_res: tuple,
    out: Path,
) -> None:
    img = frame_bgr.copy()

    def _box(b: PixelBounds, loc: tuple[int, int], tw: int, th: int, passed: bool) -> None:
        color = (0, 255, 0) if passed else (0, 0, 255)
        x1, y1 = b.left + loc[0], b.top + loc[1]
        cv2.rectangle(img, (x1, y1), (x1 + tw, y1 + th), color, 2)

    c_score, c_loc, c_pass, (ctw, cth) = compass_res
    n_score, n_loc, n_pass, (ntw, nth), n_offset = navpoint_res
    d_score, d_loc, d_pass, (dtw, dth), d_offset = destination_res

    # region outlines
    cv2.rectangle(img, (compass_b.left, compass_b.top), (compass_b.right, compass_b.bottom), (255, 0, 255), 1)
    cv2.rectangle(img, (center_b.left, center_b.top), (center_b.right, center_b.bottom), (255, 255, 0), 1)

    _box(compass_b, c_loc, ctw, cth, c_pass)
    _box(compass_b, n_loc, ntw, nth, n_pass)
    _box(center_b, d_loc, dtw, dth, d_pass)

    if n_offset:
        cx = compass_b.left + compass_b.width // 2
        cy = compass_b.top + compass_b.height // 2
        cv2.line(img, (cx, cy), (cx + int(n_offset["x"]), cy - int(n_offset["y"])), (255, 255, 0), 2)

    if d_offset:
        cx = center_b.left + center_b.width // 2
        cy = center_b.top + center_b.height // 2
        cv2.line(img, (cx, cy), (cx + int(d_offset["x"]), cy - int(d_offset["y"])), (0, 165, 255), 2)

    cv2.imwrite(str(out), img)


def main() -> None:
    parser = argparse.ArgumentParser(description="CV template match probe against live CrossOver capture")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--save-debug", metavar="PATH", help="write annotated PNG")
    parser.add_argument("--save-raw", metavar="PATH", help="write raw captured frame (for re-baking templates)")
    parser.add_argument("--threshold-compass", type=float, default=_THRESHOLD_COMPASS)
    parser.add_argument("--threshold-navpoint", type=float, default=_THRESHOLD_NAVPOINT)
    parser.add_argument("--threshold-destination", type=float, default=_THRESHOLD_DESTINATION)
    parser.add_argument("--delay", type=float, default=0.0, metavar="SECONDS",
                        help="wait before capturing (focus the game window first)")
    parser.add_argument("--open", action="store_true",
                        help="open debug image in Preview after saving (requires --save-debug)")
    args = parser.parse_args()

    if args.delay > 0:
        import time
        print(f"Capturing in {args.delay:.1f}s — focus the game window now")
        time.sleep(args.delay)

    loaded = load_config_with_fallback(args.config)
    ctx = build_runtime_context(loaded.config, include_screen_capture=True)
    if ctx.screen_capture is None:
        print("ERROR: no screen capture backend on this platform", file=sys.stderr)
        sys.exit(2)

    layout = build_capture_layout(loaded.config.screen)
    base = layout.base_bounds

    pil_img = ctx.screen_capture.capture_region(base.left, base.top, base.right, base.bottom)
    frame_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    fh, fw = frame_bgr.shape[:2]
    print(f"Capture: {fw}x{fh}px  base={base.to_dict()}")

    nr = layout.named_regions
    compass_b = nr.get("compass") or PixelBounds(
        left=round(fw * 5 / 16), top=round(fh * 5 / 8),
        right=round(fw * 2 / 4), bottom=round(fh * 15 / 16),
    )
    center_b = nr.get("center") or PixelBounds(
        left=round(fw / 3), top=round(fh / 3),
        right=round(fw * 2 / 3), bottom=round(fh * 2 / 3),
    )

    compass_crop = frame_bgr[compass_b.top:compass_b.bottom, compass_b.left:compass_b.right]
    center_crop = frame_bgr[center_b.top:center_b.bottom, center_b.left:center_b.right]
    print(f"Compass region: {compass_crop.shape[1]}x{compass_crop.shape[0]}px")
    print(f"Center region:  {center_crop.shape[1]}x{center_crop.shape[0]}px")
    print()

    tmpl = Path("templates")
    c_res = _match_compass(compass_crop, tmpl / "compass.png", args.threshold_compass)
    n_res = _match_navpoint(compass_crop, tmpl / "navpoint.png", args.threshold_navpoint)
    d_res = _match_destination(center_crop, tmpl / "destination.png", args.threshold_destination)

    c_score, c_loc, c_pass, _ = c_res
    n_score, n_loc, n_pass, _, n_offset = n_res
    d_score, d_loc, d_pass, _, d_offset = d_res

    def _pf(passed: bool) -> str:
        return "PASS" if passed else "FAIL"

    print(f"compass:     score={c_score:.4f}  loc={c_loc}  threshold={args.threshold_compass}  {_pf(c_pass)}")
    print(f"navpoint:    score={n_score:.4f}  loc={n_loc}  threshold={args.threshold_navpoint}  {_pf(n_pass)}")
    if n_offset:
        print(f"             offset x={n_offset['x']:.1f}px  y={n_offset['y']:.1f}px")
    print(f"destination: score={d_score:.4f}  loc={d_loc}  threshold={args.threshold_destination}  {_pf(d_pass)}")
    if d_offset:
        print(f"             offset x={d_offset['x']:.1f}px  y={d_offset['y']:.1f}px")

    all_pass = c_pass and n_pass and d_pass
    print()
    print("ALL PASS" if all_pass else "FAIL — re-run with --save-raw to capture frame for template re-baking")

    if args.save_raw:
        cv2.imwrite(args.save_raw, frame_bgr)
        print(f"Raw frame: {args.save_raw}")

    if args.save_debug:
        _save_debug(frame_bgr, compass_b, center_b, c_res, n_res, d_res, Path(args.save_debug))
        print(f"Debug frame: {args.save_debug}")
        if args.open:
            import subprocess
            subprocess.run(["open", args.save_debug])

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
