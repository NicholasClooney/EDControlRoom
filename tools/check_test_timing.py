from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a unittest target through 'uv run python3 -m unittest' and fail "
            "if the wall-clock runtime exceeds a threshold."
        )
    )
    parser.add_argument(
        "target",
        help="Unittest target passed to 'python3 -m unittest', e.g. tests/test_haul_loop.py",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        required=True,
        help="Maximum allowed wall-clock seconds before the check fails.",
    )
    parser.add_argument(
        "--uv-cache-dir",
        default=os.environ.get("UV_CACHE_DIR"),
        help="Optional uv cache directory override.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    if args.uv_cache_dir:
        env["UV_CACHE_DIR"] = args.uv_cache_dir

    cmd = ["uv", "run", "python3", "-m", "unittest", args.target]
    started = time.perf_counter()
    completed = subprocess.run(
        cmd,
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
    )
    elapsed = time.perf_counter() - started

    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    print(
        f"[timing] target={args.target} elapsed={elapsed:.3f}s threshold={args.max_seconds:.3f}s",
        file=sys.stderr,
    )

    if completed.returncode != 0:
        return completed.returncode
    if elapsed > args.max_seconds:
        print(
            f"[timing] runtime exceeded threshold by {elapsed - args.max_seconds:.3f}s",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
