from __future__ import annotations

import argparse
import json
import math
import sys
from time import sleep

from edap.config import ConfigError, DEFAULT_CONFIG_PATH
from edap.routines import auto_zero_throttle_on_arrival
from edap.runtime import build_runtime_context, load_config_with_fallback
from edap.ship_controls import ShipControls
from edap.state import JournalWatcher


ROUTINE_AUTO_ZERO_THROTTLE_ON_ARRIVAL = "auto_zero_throttle_on_arrival"
SUPPORTED_ROUTINES = [ROUTINE_AUTO_ZERO_THROTTLE_ON_ARRIVAL]


def _progress(message: str) -> None:
    sys.stderr.write(f"{message}\n")


def _sleep_with_countdown(routine: str, delay_seconds: float) -> None:
    remaining = int(math.ceil(delay_seconds))
    while remaining > 0:
        _progress(f"Starting {routine} in {remaining}s...")
        sleep(1)
        remaining -= 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a journal-driven routine")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config TOML file",
    )
    parser.add_argument(
        "--routine",
        required=True,
        choices=SUPPORTED_ROUTINES,
        help="Routine to run",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of times to dispatch the routine action when triggered",
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=0.0,
        help="Optional hold duration per activation for the dispatched action",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Delay before starting the watcher so you can focus the game window",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=0.5,
        help="Journal poll interval in seconds",
    )
    args = parser.parse_args()

    try:
        loaded = load_config_with_fallback(args.config)
    except FileNotFoundError:
        sys.stderr.write(
            f"Config file not found: {args.config}\n"
            f"Create `config.toml` from `config.example.toml`, or pass `--config /path/to/config.toml`.\n"
        )
        return 2
    except ConfigError as exc:
        sys.stderr.write(f"Invalid config: {exc}\n")
        return 2

    if args.poll_interval_seconds < 0:
        sys.stderr.write("Invalid routine request: --poll-interval-seconds must be non-negative\n")
        return 2

    runtime = build_runtime_context(loaded.config, actions=["SetSpeedZero"])
    journal_dir = runtime.journal.effective_path
    journal_source = runtime.journal.cli_source_status()
    if journal_dir is None:
        sys.stderr.write(
            "Could not resolve journal directory. "
            f"Source status: {journal_source}. Configure `paths.journal_dir` or ensure CrossOver auto-detection works.\n"
        )
        return 2

    bindings_file = runtime.bindings.effective_path
    bindings_source = runtime.bindings.cli_source_status()
    if bindings_file is None:
        sys.stderr.write(
            "Could not resolve bindings file. "
            f"Source status: {bindings_source}. Configure `paths.bindings_file` or ensure CrossOver auto-detection works.\n"
        )
        return 2

    if runtime.input_controller is None:
        sys.stderr.write(f"Unsupported input platform: {loaded.config.runtime.platform}\n")
        return 2

    if runtime.binding_lookup is None:
        sys.stderr.write(
            "Could not load binding lookup from resolved bindings file. "
            f"Source status: {bindings_source}.\n"
        )
        return 2

    controls = ShipControls.from_binding_lookup(
        runtime.binding_lookup,
        runtime.input_controller,
        minimum_action_hold_s=loaded.config.controls.minimum_action_hold_seconds,
        continuous_action_hold_s=loaded.config.controls.continuous_action_hold_seconds,
    )

    if args.delay_seconds > 0:
        _sleep_with_countdown(args.routine, args.delay_seconds)

    watcher = JournalWatcher(
        journal_dir,
        poll_interval_s=args.poll_interval_seconds,
    )

    _progress(
        f"Watching {journal_dir} for SupercruiseExit events "
        f"(poll {args.poll_interval_seconds:.2f}s)."
    )

    try:
        if args.routine == ROUTINE_AUTO_ZERO_THROTTLE_ON_ARRIVAL:
            result = auto_zero_throttle_on_arrival(
                controls,
                watcher.watch(),
                repeat=args.repeat,
                hold_s=args.hold_seconds,
            )
        else:
            raise RuntimeError(f"unsupported routine: {args.routine}")
    except KeyboardInterrupt:
        sys.stderr.write("Interrupted.\n")
        return 130

    payload = {
        "config_path": loaded.config_path,
        "used_example_config_fallback": loaded.used_example_config_fallback,
        "routine": args.routine,
        "journal_dir": str(journal_dir),
        "journal_source": journal_source,
        "bindings_file": str(bindings_file),
        "bindings_source": bindings_source,
        "repeat": args.repeat,
        "hold_s": args.hold_seconds,
        "poll_interval_s": args.poll_interval_seconds,
        "result": {
            "action": result.action,
            "dispatch": result.dispatch.to_dict(),
            "wait_s": result.wait_s,
            "trigger_event": result.trigger_event,
        },
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if result.dispatch.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
