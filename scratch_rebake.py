"""
Template rebake helper for the CV pipeline.

Extracts and processes the relevant screen region from a raw frame so you
can crop the element in Preview and save it back to templates/.

Usage:
    # Compass: equalized grayscale — crop the compass dial face
    uv run python3 scratch_rebake.py compass

    # Destination: orange-filtered center — crop the 3/4 circle reticle
    uv run python3 scratch_rebake.py destination

Both subcommands can capture a live frame (with optional --delay) or reuse
an existing raw PNG via --raw.  The processed region is written to --out
(default: /tmp/cv-<target>.png) and optionally opened in Preview with --open.

After saving the output, open it in Preview, select just the target element
with the rectangular selection tool, crop (Cmd+K), and save over templates/.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np


def _capture_raw(config_path: str, delay: float) -> np.ndarray:
    from edap.capture import build_capture_layout
    from edap.runtime import build_runtime_context, load_config_with_fallback

    if delay > 0:
        import time
        print(f"Capturing in {delay:.1f}s — focus the game window now", flush=True)
        time.sleep(delay)

    loaded = load_config_with_fallback(config_path)
    ctx = build_runtime_context(loaded.config, include_screen_capture=True)
    if ctx.screen_capture is None:
        print("ERROR: no screen capture backend on this platform", file=sys.stderr)
        sys.exit(2)

    layout = build_capture_layout(loaded.config.screen)
    base = layout.base_bounds
    pil_img = ctx.screen_capture.capture_region(base.left, base.top, base.right, base.bottom)
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def _load_or_capture(args) -> np.ndarray:
    if args.raw:
        frame = cv2.imread(args.raw)
        if frame is None:
            print(f"ERROR: could not read {args.raw}", file=sys.stderr)
            sys.exit(2)
        return frame
    return _capture_raw(args.config, args.delay)


def cmd_compass(args) -> None:
    frame = _load_or_capture(args)
    fh, fw = frame.shape[:2]

    l = round(fw * 5 / 16)
    t = round(fh * 5 / 8)
    r = round(fw * 2 / 4)
    b = round(fh * 15 / 16)
    region = frame[t:b, l:r]
    print(f"Frame: {fw}x{fh}  Compass region: {region.shape[1]}x{region.shape[0]}px  top-left=({l},{t})")

    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    eq = clahe.apply(gray)

    out = args.out or "/tmp/cv-compass.png"
    cv2.imwrite(out, eq)
    print(f"Wrote {out}")
    print()
    print("Open in Preview, select the compass dial face (circular ring), Cmd+K to crop,")
    print("then File → Export As → templates/compass.png")

    if args.open:
        subprocess.run(["open", out])


def cmd_destination(args) -> None:
    frame = _load_or_capture(args)
    fh, fw = frame.shape[:2]

    l = round(fw / 3)
    t = round(fh / 3)
    r = round(fw * 2 / 3)
    b = round(fh * 2 / 3)
    region = frame[t:b, l:r]
    print(f"Frame: {fw}x{fh}  Center region: {region.shape[1]}x{region.shape[0]}px  top-left=({l},{t})")

    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([10, 100, 80]), np.array([30, 255, 255]))

    out = args.out or "/tmp/cv-destination.png"
    cv2.imwrite(out, mask)
    print(f"Wrote {out}")
    print()
    print("Open in Preview, select the 3/4 circle arc (white on black), Cmd+K to crop,")
    print("then File → Export As → templates/destination.png")

    if args.open:
        subprocess.run(["open", out])


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract processed region for template re-baking")
    parser.add_argument("--config", default="config.toml")
    sub = parser.add_subparsers(dest="target", required=True)
    compass_sub = sub.add_parser("compass", help="equalized grayscale compass region")
    for s in [compass_sub]:
        s.add_argument("--raw", metavar="PATH", help="use existing raw PNG instead of capturing")
        s.add_argument("--out", metavar="PATH", help="output path (default: /tmp/cv-compass.png)")
        s.add_argument("--delay", type=float, default=0.0, metavar="SECONDS")
        s.add_argument("--open", action="store_true", help="open result in Preview automatically")

    dest_sub = sub.add_parser("destination", help="orange-filtered center region")
    dest_sub.add_argument("--raw", metavar="PATH", help="use existing raw PNG instead of capturing")
    dest_sub.add_argument("--out", metavar="PATH", help="output path (default: /tmp/cv-destination.png)")
    dest_sub.add_argument("--delay", type=float, default=0.0, metavar="SECONDS")
    dest_sub.add_argument("--open", action="store_true", help="open result in Preview automatically")

    args = parser.parse_args()

    if args.target == "compass":
        cmd_compass(args)
    elif args.target == "destination":
        cmd_destination(args)


if __name__ == "__main__":
    main()
