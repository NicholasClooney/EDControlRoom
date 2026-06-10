from __future__ import annotations

from time import monotonic
from typing import Callable

from edap.actions import ActionDispatchResult
from edap.routines._base import (
    RoutineResult,
    SupportsJumpControls,
    SupportsPollEvents,
    _is_in_supercruise_event,
    _is_starting_hyperspace_event,
    _wait_for_event,
)
from edap.routines._callbacks import ProgressCallback


def jump(
    controls: SupportsJumpControls,
    watcher: SupportsPollEvents,
    *,
    max_retries: int = 3,
    jump_hold_s: float = 1.0,
    start_timeout_s: float = 20.0,
    completion_timeout_s: float = 30.0,
    time_fn: Callable[[], float] = monotonic,
    progress_fn: ProgressCallback,
) -> RoutineResult:
    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")
    if jump_hold_s < 0:
        raise ValueError("jump_hold_s must be non-negative")
    if start_timeout_s < 0:
        raise ValueError("start_timeout_s must be non-negative")
    if completion_timeout_s < 0:
        raise ValueError("completion_timeout_s must be non-negative")

    last_dispatch: ActionDispatchResult | None = None
    last_trigger_event: dict[str, object] | None = None

    for attempt in range(1, max_retries + 1):
        progress_fn(f"Dispatching jump (attempt {attempt}/{max_retries})...")
        dispatch = controls.hyper_super_combination(hold_s=jump_hold_s)
        last_dispatch = dispatch
        if dispatch.status != "ok":
            return RoutineResult(
                action="HyperSuperCombination",
                dispatch=dispatch,
                details={"attempt": attempt, "max_retries": max_retries, "phase": "dispatch"},
            )

        progress_fn("Waiting for jump to start...")
        start_deadline = time_fn() + start_timeout_s
        start_event = _wait_for_event(
            watcher,
            predicate=_is_starting_hyperspace_event,
            deadline=start_deadline,
            time_fn=time_fn,
        )
        if start_event is None:
            progress_fn(f"Jump start timed out after {start_timeout_s:.0f}s, retrying...")
            continue

        progress_fn("Jump started, waiting for arrival...")
        completion_deadline = time_fn() + completion_timeout_s
        completion_event = _wait_for_event(
            watcher,
            predicate=_is_in_supercruise_event,
            deadline=completion_deadline,
            time_fn=time_fn,
        )
        if completion_event is None:
            progress_fn(f"Jump completion timed out after {completion_timeout_s:.0f}s, retrying...")
            continue

        system = completion_event.get("StarSystem", "")
        progress_fn(f"Arrived: {system}" if system else f"Arrived ({completion_event.get('event')})")
        last_trigger_event = completion_event
        zero_dispatch = controls.set_speed_zero()
        return RoutineResult(
            action="HyperSuperCombination",
            dispatch=zero_dispatch,
            trigger_event=completion_event,
            details={
                "attempt": attempt,
                "max_retries": max_retries,
                "jump_dispatch": dispatch.to_dict(),
                "start_event": start_event,
                "completion_event": completion_event,
                "followup_action": "SetSpeedZero",
            },
        )

    assert last_dispatch is not None
    return RoutineResult(
        action="HyperSuperCombination",
        dispatch=ActionDispatchResult(
            action="HyperSuperCombination",
            status="error",
            repeat=last_dispatch.repeat,
            hold_s=jump_hold_s,
            reason="jump did not reach in_supercruise before retry budget was exhausted",
        ),
        trigger_event=last_trigger_event,
        details={"attempts": max_retries, "phase": "timeout"},
    )
