from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from time import sleep
from typing import Callable, Iterable, Protocol

from edap.actions import ActionDispatchResult


class SupportsSetSpeedZero(Protocol):
    def set_speed_zero(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the SetSpeedZero action."""


class SupportsJumpControls(SupportsSetSpeedZero, Protocol):
    def hyper_super_combination(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the HyperSuperCombination action."""


class SupportsPollEvents(Protocol):
    def poll(self) -> list[dict[str, object]]:
        """Return newly observed journal events."""


@dataclass(frozen=True)
class RoutineResult:
    action: str
    dispatch: ActionDispatchResult
    wait_s: float = 0.0
    trigger_event: dict[str, object] | None = None
    details: dict[str, object] | None = None


def set_speed_zero_then_wait(
    controls: SupportsSetSpeedZero,
    *,
    repeat: int = 1,
    hold_s: float = 0.0,
    wait_s: float = 0.0,
    sleeper: Callable[[float], None] = sleep,
) -> RoutineResult:
    if wait_s < 0:
        raise ValueError("wait_s must be non-negative")

    dispatch = controls.set_speed_zero(repeat=repeat, hold_s=hold_s)
    if dispatch.status == "ok" and wait_s > 0:
        sleeper(wait_s)

    return RoutineResult(
        action="SetSpeedZero",
        dispatch=dispatch,
        wait_s=wait_s,
    )


def auto_zero_throttle_on_arrival(
    controls: SupportsSetSpeedZero,
    events: Iterable[dict[str, object]],
    *,
    repeat: int = 1,
    hold_s: float = 0.0,
) -> RoutineResult:
    for event in events:
        if event.get("event") != "SupercruiseExit":
            continue

        dispatch = controls.set_speed_zero(repeat=repeat, hold_s=hold_s)
        return RoutineResult(
            action="SetSpeedZero",
            dispatch=dispatch,
            trigger_event=event,
        )

    raise RuntimeError("event stream ended before SupercruiseExit was observed")


def jump(
    controls: SupportsJumpControls,
    watcher: SupportsPollEvents,
    *,
    max_retries: int = 3,
    jump_hold_s: float = 1.0,
    start_timeout_s: float = 20.0,
    completion_timeout_s: float = 30.0,
    time_fn: Callable[[], float] = monotonic,
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
        dispatch = controls.hyper_super_combination(hold_s=jump_hold_s)
        last_dispatch = dispatch
        if dispatch.status != "ok":
            return RoutineResult(
                action="HyperSuperCombination",
                dispatch=dispatch,
                details={"attempt": attempt, "max_retries": max_retries, "phase": "dispatch"},
            )

        start_deadline = time_fn() + start_timeout_s
        start_event = _wait_for_event(
            watcher,
            predicate=_is_starting_hyperspace_event,
            deadline=start_deadline,
            time_fn=time_fn,
        )
        if start_event is None:
            continue

        completion_deadline = time_fn() + completion_timeout_s
        completion_event = _wait_for_event(
            watcher,
            predicate=_is_in_supercruise_event,
            deadline=completion_deadline,
            time_fn=time_fn,
        )
        if completion_event is None:
            continue

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


def _wait_for_event(
    watcher: SupportsPollEvents,
    *,
    predicate: Callable[[dict[str, object]], bool],
    deadline: float,
    time_fn: Callable[[], float],
) -> dict[str, object] | None:
    while time_fn() <= deadline:
        for event in watcher.poll():
            if predicate(event):
                return event
    return None


def _is_starting_hyperspace_event(event: dict[str, object]) -> bool:
    return event.get("event") == "StartJump" and str(event.get("JumpType", "")).lower() == "hyperspace"


def _is_in_supercruise_event(event: dict[str, object]) -> bool:
    return event.get("event") in {"SupercruiseEntry", "FSDJump"}
