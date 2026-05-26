from __future__ import annotations

import argparse
import json
import math
import sys
from time import sleep

from edap.config import ConfigError, DEFAULT_CONFIG_PATH, EXAMPLE_CONFIG_PATH, load_config
from edap.platform.input.factory import build_input_controller
from edap.platform.paths.factory import build_game_paths
from edap.ship_controls import ShipControls


def _load_config_with_fallback(config_path: str):
    try:
        return load_config(config_path), config_path, False
    except FileNotFoundError:
        if config_path == str(DEFAULT_CONFIG_PATH) and EXAMPLE_CONFIG_PATH.exists():
            return load_config(EXAMPLE_CONFIG_PATH), str(EXAMPLE_CONFIG_PATH), True
        raise


def _resolve_bindings_file(config) -> tuple[str | None, str]:
    if config.paths.bindings_file:
        if config.paths.bindings_file.exists():
            return str(config.paths.bindings_file), "configured"
        return None, "configured_missing"

    game_paths = build_game_paths(config.runtime.platform)
    if game_paths is None:
        return None, "unsupported_platform"

    bindings_file = game_paths.default_bindings_file()
    if bindings_file is None:
        return None, "auto_detect_not_found"
    return str(bindings_file), "auto_detected"


def _progress(message: str) -> None:
    sys.stderr.write(f"{message}\n")


def _sleep_with_countdown(action: str, delay_seconds: float) -> None:
    remaining = int(math.ceil(delay_seconds))
    while remaining > 0:
        _progress(f"Sending {action} in {remaining}s...")
        sleep(1)
        remaining -= 1


def _report_repeat_plan(action: str, repeat: int, hold_s: float) -> None:
    if repeat == 1:
        _progress(f"Sending {action} once (hold {hold_s:.2f}s).")
        return
    _progress(f"Sending {action} {repeat} times (hold {hold_s:.2f}s each).")


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
        "--repeat",
        type=int,
        default=1,
        help="Number of times to send the action",
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=0.0,
        help="Optional hold duration per tap",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Delay before sending the action so you can focus the game window",
    )
    args = parser.parse_args()

    try:
        config, config_path, using_fallback = _load_config_with_fallback(args.config)
    except FileNotFoundError:
        sys.stderr.write(
            f"Config file not found: {args.config}\n"
            f"Create `config.toml` from `config.example.toml`, or pass `--config /path/to/config.toml`.\n"
        )
        return 2
    except ConfigError as exc:
        sys.stderr.write(f"Invalid config: {exc}\n")
        return 2

    bindings_file, bindings_source = _resolve_bindings_file(config)
    if bindings_file is None:
        sys.stderr.write(
            "Could not resolve bindings file. "
            f"Source status: {bindings_source}. Configure `paths.bindings_file` or ensure CrossOver auto-detection works.\n"
        )
        return 2

    input_controller = build_input_controller(config.runtime.platform)
    if input_controller is None:
        sys.stderr.write(f"Unsupported input platform: {config.runtime.platform}\n")
        return 2

    controls = ShipControls.from_bindings_file(bindings_file, input_controller, actions=[args.action])
    if args.delay_seconds > 0:
        _sleep_with_countdown(args.action, args.delay_seconds)
    _report_repeat_plan(args.action, args.repeat, args.hold_seconds)
    result = controls.tap_action(args.action, repeat=args.repeat, hold_s=args.hold_seconds)

    payload = {
        "config_path": config_path,
        "used_example_config_fallback": using_fallback,
        "bindings_file": bindings_file,
        "bindings_source": bindings_source,
        "result": result.to_dict(),
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
