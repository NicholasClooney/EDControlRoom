from __future__ import annotations

from time import sleep
from typing import Callable, Iterable

from edap.routines._base import RoutineResult, SupportsSetSpeedZero
from edap.routines._callbacks import ProgressCallback


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
    progress_fn: ProgressCallback,
) -> RoutineResult:
    for event in events:
        if event.get("event") != "SupercruiseExit":
            continue

        system = event.get("StarSystem", "")
        progress_fn(f"SupercruiseExit: {system}" if system else "SupercruiseExit")
        dispatch = controls.set_speed_zero(repeat=repeat, hold_s=hold_s)
        return RoutineResult(
            action="SetSpeedZero",
            dispatch=dispatch,
            trigger_event=event,
        )

    raise RuntimeError("event stream ended before SupercruiseExit was observed")
