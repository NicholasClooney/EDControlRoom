from __future__ import annotations

import argparse
import io
import json
import sys
import time
import unittest
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass(frozen=True)
class TestTiming:
    test_id: str
    seconds: float
    outcome: str


class TimingTextTestResult(unittest.TextTestResult):
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.timings: list[TestTiming] = []
        self._started_at: float | None = None
        self._outcome_by_id: dict[str, str] = {}

    def startTest(self, test: unittest.case.TestCase) -> None:
        self._started_at = time.perf_counter()
        super().startTest(test)

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        self._outcome_by_id[test.id()] = "ok"
        super().addSuccess(test)

    def addFailure(self, test: unittest.case.TestCase, err) -> None:
        self._outcome_by_id[test.id()] = "failure"
        super().addFailure(test, err)

    def addError(self, test: unittest.case.TestCase, err) -> None:
        self._outcome_by_id[test.id()] = "error"
        super().addError(test, err)

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        self._outcome_by_id[test.id()] = "skipped"
        super().addSkip(test, reason)

    def addExpectedFailure(self, test: unittest.case.TestCase, err) -> None:
        self._outcome_by_id[test.id()] = "expected_failure"
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test: unittest.case.TestCase) -> None:
        self._outcome_by_id[test.id()] = "unexpected_success"
        super().addUnexpectedSuccess(test)

    def stopTest(self, test: unittest.case.TestCase) -> None:
        started_at = self._started_at
        elapsed = 0.0 if started_at is None else time.perf_counter() - started_at
        self.timings.append(
            TestTiming(
                test_id=test.id(),
                seconds=elapsed,
                outcome=self._outcome_by_id.get(test.id(), "unknown"),
            )
        )
        super().stopTest(test)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run unittest and report per-test timings, sorted and filtered for the slowest cases."
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help=(
            "Optional unittest targets. If omitted, the script runs discovery. "
            "Examples: tests.test_runtime test_haul_loop.HaulLoopTests.test_one_iteration_happy_path"
        ),
    )
    parser.add_argument(
        "--start-directory",
        default="tests",
        help="Directory used for unittest discovery when no explicit targets are provided.",
    )
    parser.add_argument(
        "--pattern",
        default="test*.py",
        help="Filename pattern used for unittest discovery.",
    )
    parser.add_argument(
        "--top-level-directory",
        default=None,
        help="Optional top-level directory passed to unittest discovery.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="How many rows to report after sorting and filtering. Default: 10.",
    )
    parser.add_argument(
        "--sort",
        choices=("slowest", "fastest", "name"),
        default="slowest",
        help="Sort order for the report. Default: slowest.",
    )
    parser.add_argument(
        "--min-seconds",
        type=float,
        default=0.0,
        help="Only include tests at or above this runtime threshold.",
    )
    parser.add_argument(
        "--outcome",
        choices=("all", "ok", "failure", "error", "skipped"),
        default="all",
        help="Filter by unittest outcome. Default: all.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the timing report as JSON.",
    )
    return parser.parse_args()


def build_suite(args: argparse.Namespace) -> unittest.TestSuite:
    loader = unittest.defaultTestLoader
    if args.targets:
        return loader.loadTestsFromNames(args.targets)
    return loader.discover(
        start_dir=args.start_directory,
        pattern=args.pattern,
        top_level_dir=args.top_level_directory,
    )


def sort_timings(timings: list[TestTiming], sort_key: str) -> list[TestTiming]:
    if sort_key == "fastest":
        return sorted(timings, key=lambda item: (item.seconds, item.test_id))
    if sort_key == "name":
        return sorted(timings, key=lambda item: item.test_id)
    return sorted(timings, key=lambda item: (-item.seconds, item.test_id))


def filter_timings(
    timings: list[TestTiming],
    *,
    min_seconds: float,
    outcome: str,
) -> list[TestTiming]:
    filtered = [item for item in timings if item.seconds >= min_seconds]
    if outcome != "all":
        filtered = [item for item in filtered if item.outcome == outcome]
    return filtered


def build_report_lines(
    timings: list[TestTiming],
    *,
    top: int,
    sort_key: str,
    min_seconds: float,
    outcome: str,
    total_tests: int,
    total_seconds: float,
    failed: bool,
) -> list[str]:
    filtered = filter_timings(timings, min_seconds=min_seconds, outcome=outcome)
    ordered = sort_timings(filtered, sort_key)[:top]

    lines = [
        (
            "suite_status={status} total_tests={total_tests} total_seconds={total_seconds:.3f} "
            "reported={reported} sort={sort_key} min_seconds={min_seconds:.3f} outcome={outcome}"
        ).format(
            status="failed" if failed else "ok",
            total_tests=total_tests,
            total_seconds=total_seconds,
            reported=len(ordered),
            sort_key=sort_key,
            min_seconds=min_seconds,
            outcome=outcome,
        )
    ]
    for index, item in enumerate(ordered, start=1):
        lines.append(f"{index:>2}. {item.seconds:>7.3f}s  [{item.outcome}]  {item.test_id}")
    return lines


def main() -> int:
    args = parse_args()
    suite = build_suite(args)
    stream = io.StringIO()
    runner = unittest.TextTestRunner(
        stream=stream,
        verbosity=0,
        resultclass=TimingTextTestResult,
    )
    started = time.perf_counter()
    result: TimingTextTestResult = runner.run(suite)
    total_seconds = time.perf_counter() - started

    if args.json:
        payload = {
            "suite_status": "failed" if not result.wasSuccessful() else "ok",
            "total_tests": result.testsRun,
            "total_seconds": total_seconds,
            "sort": args.sort,
            "min_seconds": args.min_seconds,
            "outcome": args.outcome,
            "top": args.top,
            "timings": [
                asdict(item)
                for item in sort_timings(
                    filter_timings(result.timings, min_seconds=args.min_seconds, outcome=args.outcome),
                    args.sort,
                )[: args.top]
            ],
            "failures": [test.id() for test, _ in result.failures],
            "errors": [test.id() for test, _ in result.errors],
        }
        print(json.dumps(payload, indent=2))
    else:
        for line in build_report_lines(
            result.timings,
            top=args.top,
            sort_key=args.sort,
            min_seconds=args.min_seconds,
            outcome=args.outcome,
            total_tests=result.testsRun,
            total_seconds=total_seconds,
            failed=not result.wasSuccessful(),
        ):
            print(line)
        if result.failures:
            print("failures:")
            for test, _ in result.failures:
                print(f"  - {test.id()}")
        if result.errors:
            print("errors:")
            for test, _ in result.errors:
                print(f"  - {test.id()}")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
