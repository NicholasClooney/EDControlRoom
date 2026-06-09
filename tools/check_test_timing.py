from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
def _add_shared_args(parser: argparse.ArgumentParser) -> None:
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


def parse_args() -> argparse.Namespace:
    pre_parser = argparse.ArgumentParser(add_help=False)
    _add_shared_args(pre_parser)
    shared_args, remaining = pre_parser.parse_known_args()

    parser = argparse.ArgumentParser(
        description=(
            "Run a unittest target through 'uv run python3 -m unittest' and fail "
            "if the wall-clock runtime exceeds a threshold."
        )
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    target_parser = subparsers.add_parser(
        "target",
        help="Time a single unittest target.",
    )
    target_parser.add_argument(
        "target",
        help="Unittest target passed to 'python3 -m unittest', e.g. tests/test_haul_two_way.py",
    )

    discover_parser = subparsers.add_parser(
        "discover",
        help="Time unittest discovery.",
    )
    discover_parser.add_argument(
        "--start-directory",
        default="tests",
        help="Directory passed to 'python3 -m unittest discover -s ...'.",
    )
    discover_parser.add_argument(
        "--pattern",
        default=None,
        help="Optional filename pattern passed to discovery via '-p'.",
    )
    discover_parser.add_argument(
        "--top-level-directory",
        default=None,
        help="Optional top-level directory passed to discovery via '-t'.",
    )
    args = parser.parse_args(remaining)
    args.max_seconds = shared_args.max_seconds
    args.uv_cache_dir = shared_args.uv_cache_dir
    return args


def build_unittest_args(args: argparse.Namespace) -> tuple[list[str], str]:
    if args.mode == "target":
        return [args.target], args.target

    unittest_args = ["discover", "-s", args.start_directory]
    label = f"discover:{args.start_directory}"
    if args.pattern:
        unittest_args.extend(["-p", args.pattern])
        label += f" pattern={args.pattern}"
    if args.top_level_directory:
        unittest_args.extend(["-t", args.top_level_directory])
        label += f" top={args.top_level_directory}"
    return unittest_args, label


def main() -> int:
    args = parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    if args.uv_cache_dir:
        env["UV_CACHE_DIR"] = args.uv_cache_dir

    unittest_args, label = build_unittest_args(args)
    cmd = ["uv", "run", "python3", "-m", "unittest", *unittest_args]
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
        f"[timing] target={label} elapsed={elapsed:.3f}s threshold={args.max_seconds:.3f}s",
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
