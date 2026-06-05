from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from time import sleep

from edap.binding_lookup import BindingLookup
from edap.config import ConfigError, DEFAULT_CONFIG_PATH
from edap.routines import auto_zero_throttle_on_arrival, dock, jump, station_refuel_menu
from edap.runtime import build_runtime_context, load_config_with_fallback
from edap.ship_controls import ShipControls
from edap.state import JournalWatcher


ROUTINE_AUTO_ZERO_THROTTLE_ON_ARRIVAL = "auto_zero_throttle_on_arrival"
ROUTINE_JUMP = "jump"
ROUTINE_DOCK = "dock"
ROUTINE_STATION_REFUEL_MENU = "station_refuel_menu"
SUPPORTED_ROUTINES = [ROUTINE_AUTO_ZERO_THROTTLE_ON_ARRIVAL, ROUTINE_JUMP, ROUTINE_DOCK, ROUTINE_STATION_REFUEL_MENU]
DEFAULT_EVENT_LOG_PATH = Path("artifacts/run-routine-events.log")


def _progress(message: str) -> None:
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()


def _make_logging_sleeper(progress_fn):
    def _sleeper(s: float) -> None:
        progress_fn(f"  pause {s:g}s")
        sleep(s)
    return _sleeper


def _sleep_with_countdown(routine: str, delay_seconds: float) -> None:
    remaining = int(math.ceil(delay_seconds))
    while remaining > 0:
        _progress(f"Starting {routine} in {remaining}s...")
        sleep(1)
        remaining -= 1


def _describe_binding(binding_lookup: BindingLookup, action: str) -> str:
    resolved = binding_lookup.resolve(action)
    if resolved.status != "ok" or resolved.binding is None:
        reason = resolved.reason or resolved.status
        return f"{action} unresolved ({reason})"

    parts = [resolved.binding.key]
    if resolved.binding.modifier:
        parts.insert(0, resolved.binding.modifier)
    return f"{action} -> {'+'.join(parts)}"


class LoggingJournalWatcher:
    def __init__(self, watcher: JournalWatcher, log_path: Path | None) -> None:
        self._watcher = watcher
        self._log_path = log_path
        self._log_handle = None

        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = log_path.open("a", encoding="utf-8")

    def watch(self):
        for event in self._watcher.watch():
            self._log_event(event)
            yield event

    def poll(self) -> list[dict[str, object]]:
        events = self._watcher.poll()
        for event in events:
            self._log_event(event)
        return events

    def close(self) -> None:
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def _log_event(self, event: dict[str, object]) -> None:
        if self._log_handle is None:
            return
        self._log_handle.write(json.dumps(event))
        self._log_handle.write("\n")
        self._log_handle.flush()


class ProgressShipControls:
    """Wraps ShipControls to log each key dispatch to stderr."""

    def __init__(self, controls: ShipControls, progress_fn) -> None:
        self._controls = controls
        self._progress = progress_fn

    def _log(self, action: str, repeat: int) -> None:
        suffix = f" x{repeat}" if repeat > 1 else ""
        self._progress(f"  key: {action}{suffix}")

    def set_speed_zero(self, repeat: int = 1, hold_s: float | None = None):
        self._log("SetSpeedZero", repeat)
        return self._controls.set_speed_zero(repeat=repeat, hold_s=hold_s)

    def hyper_super_combination(self, repeat: int = 1, hold_s: float | None = None):
        self._log("HyperSuperCombination", repeat)
        return self._controls.hyper_super_combination(repeat=repeat, hold_s=hold_s)

    def focus_left_panel(self, repeat: int = 1, hold_s: float | None = None):
        self._log("FocusLeftPanel", repeat)
        return self._controls.focus_left_panel(repeat=repeat, hold_s=hold_s)

    def ui_back(self, repeat: int = 1, hold_s: float | None = None):
        self._log("UI_Back", repeat)
        return self._controls.ui_back(repeat=repeat, hold_s=hold_s)

    def cycle_next_panel(self, repeat: int = 1, hold_s: float | None = None):
        self._log("CycleNextPanel", repeat)
        return self._controls.cycle_next_panel(repeat=repeat, hold_s=hold_s)

    def cycle_previous_panel(self, repeat: int = 1, hold_s: float | None = None):
        self._log("CyclePreviousPanel", repeat)
        return self._controls.cycle_previous_panel(repeat=repeat, hold_s=hold_s)

    def ui_right(self, repeat: int = 1, hold_s: float | None = None):
        self._log("UI_Right", repeat)
        return self._controls.ui_right(repeat=repeat, hold_s=hold_s)

    def ui_up(self, repeat: int = 1, hold_s: float | None = None):
        self._log("UI_Up", repeat)
        return self._controls.ui_up(repeat=repeat, hold_s=hold_s)

    def ui_select(self, repeat: int = 1, hold_s: float | None = None):
        self._log("UI_Select", repeat)
        return self._controls.ui_select(repeat=repeat, hold_s=hold_s)

    def ui_down(self, repeat: int = 1, hold_s: float | None = None):
        self._log("UI_Down", repeat)
        return self._controls.ui_down(repeat=repeat, hold_s=hold_s)


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
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum attempts for retrying routines such as jump",
    )
    parser.add_argument(
        "--start-timeout-seconds",
        type=float,
        default=20.0,
        help="Maximum time to wait for a jump to start",
    )
    parser.add_argument(
        "--completion-timeout-seconds",
        type=float,
        default=30.0,
        help="Maximum time to wait for a started jump to reach in_supercruise",
    )
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=2.0,
        help="Post-trigger settle delay before a routine sends follow-up inputs",
    )
    parser.add_argument(
        "--step-delay-seconds",
        type=float,
        default=None,
        help="Delay between individual key presses in the docking request menu sequence (overrides config)",
    )
    parser.add_argument(
        "--dock-timeout-seconds",
        type=float,
        default=120.0,
        help="Maximum time to wait for a Docked event for station routines",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=20.0,
        help="Maximum time to wait for a docking request or grant after sending the dock menu sequence",
    )
    parser.add_argument(
        "--skip-supercruise-exit",
        action="store_true",
        help="Start the dock routine immediately instead of waiting for SupercruiseExit first",
    )
    parser.add_argument(
        "--auto-refuel",
        action="store_true",
        help="After Docked, run the station refuel menu sequence automatically",
    )
    parser.add_argument(
        "--log-events",
        action="store_true",
        help="Log all watched journal events to a file while the routine runs",
    )
    parser.add_argument(
        "--event-log-path",
        default=str(DEFAULT_EVENT_LOG_PATH),
        help="Path for --log-events output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write the result as JSON to stdout (for scripting)",
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

    step_delay_seconds = (
        args.step_delay_seconds
        if args.step_delay_seconds is not None
        else loaded.config.controls.step_delay_seconds
    )

    if args.poll_interval_seconds < 0:
        sys.stderr.write("Invalid routine request: --poll-interval-seconds must be non-negative\n")
        return 2
    if args.max_retries < 1:
        sys.stderr.write("Invalid routine request: --max-retries must be at least 1\n")
        return 2
    if args.start_timeout_seconds < 0:
        sys.stderr.write("Invalid routine request: --start-timeout-seconds must be non-negative\n")
        return 2
    if args.completion_timeout_seconds < 0:
        sys.stderr.write("Invalid routine request: --completion-timeout-seconds must be non-negative\n")
        return 2
    if args.settle_seconds < 0:
        sys.stderr.write("Invalid routine request: --settle-seconds must be non-negative\n")
        return 2
    if step_delay_seconds < 0:
        sys.stderr.write("Invalid routine request: --step-delay-seconds must be non-negative\n")
        return 2
    if args.dock_timeout_seconds < 0:
        sys.stderr.write("Invalid routine request: --dock-timeout-seconds must be non-negative\n")
        return 2
    if args.request_timeout_seconds < 0:
        sys.stderr.write("Invalid routine request: --request-timeout-seconds must be non-negative\n")
        return 2

    routine_actions = ["SetSpeedZero"]
    if args.routine == ROUTINE_JUMP:
        routine_actions = ["SetSpeedZero", "HyperSuperCombination"]
    elif args.routine == ROUTINE_DOCK:
        routine_actions = [
            "SetSpeedZero",
            "FocusLeftPanel",
            "UI_Back",
            "CycleNextPanel",
            "CyclePreviousPanel",
            "UI_Up",
            "UI_Right",
            "UI_Select",
            "UI_Down",
        ]
    elif args.routine == ROUTINE_STATION_REFUEL_MENU:
        routine_actions = ["UI_Up", "UI_Select", "UI_Down"]

    runtime = build_runtime_context(loaded.config, actions=routine_actions)
    journal_dir = runtime.journal.effective_path
    journal_source = runtime.journal.cli_source_status()
    routine_needs_journal = args.routine in {
        ROUTINE_AUTO_ZERO_THROTTLE_ON_ARRIVAL,
        ROUTINE_JUMP,
        ROUTINE_DOCK,
        ROUTINE_STATION_REFUEL_MENU,
    }
    if routine_needs_journal and journal_dir is None:
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
    logging_controls = ProgressShipControls(controls, _progress)
    logging_sleeper = _make_logging_sleeper(_progress)

    if args.delay_seconds > 0:
        _sleep_with_countdown(args.routine, args.delay_seconds)

    watcher = None
    if routine_needs_journal and journal_dir is not None:
        watcher = LoggingJournalWatcher(
            JournalWatcher(
                journal_dir,
                poll_interval_s=args.poll_interval_seconds,
            ),
            Path(args.event_log_path) if args.log_events else None,
        )
        watch_target = "SupercruiseExit events"
        if args.routine == ROUTINE_JUMP:
            watch_target = "hyperspace jump events"
        elif args.routine == ROUTINE_DOCK:
            watch_target = "approach and docking events"
        elif args.routine == ROUTINE_STATION_REFUEL_MENU:
            watch_target = "Docked events"
        _progress(
            f"Watching {journal_dir} for {watch_target} "
            f"(poll {args.poll_interval_seconds:.2f}s)."
        )
        if args.log_events:
            _progress(f"Logging raw journal events to {args.event_log_path}")
    _progress("Bindings:")
    if args.routine == ROUTINE_AUTO_ZERO_THROTTLE_ON_ARRIVAL:
        _progress(f"  {_describe_binding(runtime.binding_lookup, 'SetSpeedZero')}")
    elif args.routine == ROUTINE_JUMP:
        _progress(f"  {_describe_binding(runtime.binding_lookup, 'HyperSuperCombination')}")
        _progress(f"  {_describe_binding(runtime.binding_lookup, 'SetSpeedZero')}")
    elif args.routine == ROUTINE_DOCK:
        actions = [
            "FocusLeftPanel",
            "UI_Back",
            "CycleNextPanel",
            "CyclePreviousPanel",
            "UI_Up",
            "UI_Right",
            "UI_Select",
            "SetSpeedZero",
        ]
        if args.auto_refuel:
            actions.append("UI_Down")
        for action in actions:
            _progress(f"  {_describe_binding(runtime.binding_lookup, action)}")
    elif args.routine == ROUTINE_STATION_REFUEL_MENU:
        _progress(f"  {_describe_binding(runtime.binding_lookup, 'UI_Up')}")
        _progress(f"  {_describe_binding(runtime.binding_lookup, 'UI_Select')}")
        _progress(f"  {_describe_binding(runtime.binding_lookup, 'UI_Down')}")

    try:
        if args.routine == ROUTINE_AUTO_ZERO_THROTTLE_ON_ARRIVAL:
            result = auto_zero_throttle_on_arrival(
                logging_controls,
                watcher.watch(),
                repeat=args.repeat,
                hold_s=args.hold_seconds,
                progress_fn=_progress,
            )
        elif args.routine == ROUTINE_JUMP:
            result = jump(
                logging_controls,
                watcher,
                max_retries=args.max_retries,
                jump_hold_s=args.hold_seconds if args.hold_seconds > 0 else 1.0,
                start_timeout_s=args.start_timeout_seconds,
                completion_timeout_s=args.completion_timeout_seconds,
                progress_fn=_progress,
            )
        elif args.routine == ROUTINE_DOCK:
            result = dock(
                logging_controls,
                watcher,
                wait_for_supercruise_exit=not args.skip_supercruise_exit,
                auto_refuel=args.auto_refuel,
                max_retries=args.max_retries,
                request_timeout_s=args.request_timeout_seconds,
                dock_timeout_s=args.dock_timeout_seconds,
                settle_s=args.settle_seconds,
                step_delay_s=step_delay_seconds,
                sleeper=logging_sleeper,
                progress_fn=_progress,
            )
        elif args.routine == ROUTINE_STATION_REFUEL_MENU:
            result = station_refuel_menu(
                logging_controls,
                watcher,
                dock_timeout_s=args.dock_timeout_seconds,
                settle_s=args.settle_seconds,
                sleeper=logging_sleeper,
                progress_fn=_progress,
            )
        else:
            raise RuntimeError(f"unsupported routine: {args.routine}")
    except KeyboardInterrupt:
        if watcher is not None:
            watcher.close()
        sys.stderr.write("Interrupted.\n")
        return 130
    finally:
        if watcher is not None:
            watcher.close()

    status_label = "ok" if result.dispatch.status == "ok" else result.dispatch.status
    _progress(f"Done: {result.action} ({status_label})")

    if args.json:
        payload = {
            "config_path": loaded.config_path,
            "used_example_config_fallback": loaded.used_example_config_fallback,
            "routine": args.routine,
            "journal_dir": str(journal_dir) if journal_dir is not None else None,
            "journal_source": journal_source,
            "bindings_file": str(bindings_file),
            "bindings_source": bindings_source,
            "repeat": args.repeat,
            "hold_s": args.hold_seconds,
            "poll_interval_s": args.poll_interval_seconds,
            "settle_s": args.settle_seconds,
            "dock_timeout_s": args.dock_timeout_seconds,
            "request_timeout_s": args.request_timeout_seconds,
            "skip_supercruise_exit": args.skip_supercruise_exit,
            "auto_refuel": args.auto_refuel,
            "event_log_path": args.event_log_path if args.log_events and routine_needs_journal else None,
            "result": {
                "action": result.action,
                "dispatch": result.dispatch.to_dict(),
                "wait_s": result.wait_s,
                "trigger_event": result.trigger_event,
                "details": result.details,
            },
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0 if result.dispatch.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
