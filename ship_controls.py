from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from time import sleep

from edap.config import ConfigError, DEFAULT_CONFIG_PATH
from edap.runtime import build_runtime_context, load_config_with_fallback
from edap.ship_controls import ShipControls


def _progress(message: str) -> None:
    sys.stderr.write(f"{message}\n")


@dataclass(frozen=True)
class SequenceStep:
    action: str
    repeat: int | None = None
    hold_s: float | None = None
    total_s: float | None = None
    delay_s: float | None = None


def _sleep_with_countdown(action: str, delay_seconds: float) -> None:
    remaining = int(math.ceil(delay_seconds))
    while remaining > 0:
        _progress(f"Sending {action} in {remaining}s...")
        sleep(1)
        remaining -= 1


def _report_repeat_plan(action: str, repeat: int, hold_s: float, total_s: float | None = None) -> None:
    if total_s is not None:
        _progress(
            f"Planned {action} for total {total_s:.2f}s as {repeat} activations "
            f"at {hold_s:.2f}s each."
        )
        return
    if repeat == 1:
        _progress(f"Sending {action} once (hold {hold_s:.2f}s).")
        return
    _progress(f"Sending {action} {repeat} times (hold {hold_s:.2f}s each).")


def _parse_sequence(sequence: str) -> list[SequenceStep]:
    steps: list[SequenceStep] = []
    for raw_step in sequence.split(";"):
        step_text = raw_step.strip()
        if not step_text:
            continue
        parts = step_text.split()
        action = parts[0]
        repeat: int | None = None
        hold_s: float | None = None
        total_s: float | None = None
        delay_s: float | None = None
        for token in parts[1:]:
            if "=" not in token:
                raise ValueError(f"invalid sequence token: {token}")
            key, value = token.split("=", 1)
            if key == "repeat":
                repeat = int(value)
            elif key == "hold":
                hold_s = float(value)
            elif key == "total":
                total_s = float(value)
            elif key == "delay":
                delay_s = float(value)
            else:
                raise ValueError(f"unsupported sequence field: {key}")
        steps.append(SequenceStep(action=action, repeat=repeat, hold_s=hold_s, total_s=total_s, delay_s=delay_s))
    if not steps:
        raise ValueError("sequence must contain at least one action")
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual ship control entry points")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config TOML file",
    )
    parser.add_argument(
        "--action",
        default="SetSpeedZero",
        help="Elite action name to send, for example SetSpeedZero or RollLeftButton",
    )
    parser.add_argument(
        "--sequence",
        default=None,
        help=(
            "Semicolon-separated action sequence. "
            "Example: 'SetSpeedZero; RollLeftButton total=0.45; SetSpeed100'. "
            "Per-step fields: repeat=<n> hold=<seconds> total=<seconds> delay=<seconds>."
        ),
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of times to send the action",
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=None,
        help="Optional hold duration per activation. If omitted, continuous controls use config defaults.",
    )
    parser.add_argument(
        "--total-seconds",
        type=float,
        default=None,
        help="Total actuation time for continuous controls. The command will plan repeated activations from this.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Delay before sending the action so you can focus the game window",
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

    try:
        sequence_steps = _parse_sequence(args.sequence) if args.sequence else [SequenceStep(action=args.action)]
    except ValueError as exc:
        sys.stderr.write(f"Invalid sequence: {exc}\n")
        return 2

    runtime = build_runtime_context(loaded.config, actions=[step.action for step in sequence_steps])
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
        _sleep_with_countdown(sequence_steps[0].action, args.delay_seconds)

    results: list[dict[str, object]] = []
    exit_code = 0
    for index, step in enumerate(sequence_steps, start=1):
        if step.delay_s is not None and step.delay_s > 0:
            _sleep_with_countdown(step.action, step.delay_s)
        try:
            plan = controls.plan_action(
                step.action,
                repeat=step.repeat if step.repeat is not None else args.repeat,
                hold_s=step.hold_s if step.hold_s is not None else args.hold_seconds,
                total_s=step.total_s if step.total_s is not None else args.total_seconds,
            )
        except ValueError as exc:
            sys.stderr.write(f"Invalid control request at step {index} ({step.action}): {exc}\n")
            return 2

        _progress(f"Step {index}/{len(sequence_steps)}")
        _report_repeat_plan(plan.action, plan.repeat, plan.hold_s, total_s=plan.total_s)
        result = controls.dispatch_action(
            step.action,
            repeat=step.repeat if step.repeat is not None else args.repeat,
            hold_s=step.hold_s if step.hold_s is not None else args.hold_seconds,
            total_s=step.total_s if step.total_s is not None else args.total_seconds,
        )
        results.append(
            {
                "action": plan.action,
                "repeat": plan.repeat,
                "hold_s": plan.hold_s,
                "total_s": plan.total_s,
                "delay_s": step.delay_s,
                "result": result.to_dict(),
            }
        )
        if result.status != "ok":
            exit_code = 1

    payload = {
        "config_path": loaded.config_path,
        "used_example_config_fallback": loaded.used_example_config_fallback,
        "bindings_file": str(bindings_file),
        "bindings_source": bindings_source,
        "sequence": args.sequence is not None,
        "results": results,
    }
    if len(results) == 1:
        payload["result"] = results[0]["result"]
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
