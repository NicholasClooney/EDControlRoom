from __future__ import annotations

from pathlib import Path
from time import sleep
from typing import Callable

from edap.actions import ActionDispatchResult
from edap.routines._base import RoutineResult, SupportsEscapeControls
from edap.routines._callbacks import ProgressCallback
from edap.status import read_status


def escape_mass_lock(
    controls: SupportsEscapeControls,
    *,
    journal_dir: Path,
    boost_delay_s: float = 5.0,
    step_delay_s: float = 0.3,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: ProgressCallback,
) -> RoutineResult:
    if boost_delay_s < 0:
        raise ValueError("boost_delay_s must be non-negative")
    if step_delay_s < 0:
        raise ValueError("step_delay_s must be non-negative")

    progress_fn("Setting speed 100 to break auto-undock...")
    speed_result = controls.set_speed_full()
    if speed_result.status != "ok":
        progress_fn(f"Warning: SetSpeed100 dispatch failed: {speed_result.reason}")
    if step_delay_s > 0:
        sleeper(step_delay_s)

    boost_count = 0
    last_boost: ActionDispatchResult | None = None

    while True:
        status = read_status(journal_dir)
        if status is None or not status.flags.fsd_mass_locked:
            break
        progress_fn("FSD mass locked -- boosting away...")
        last_boost = controls.boost()
        if last_boost.status != "ok":
            progress_fn(f"Warning: UseBoostJuice dispatch failed: {last_boost.reason}")
        boost_count += 1
        if boost_delay_s > 0:
            sleeper(boost_delay_s)

    dispatch = last_boost or ActionDispatchResult(
        action="EscapeMassLock",
        status="ok",
        reason="not mass locked",
    )
    return RoutineResult(
        action="EscapeMassLock",
        dispatch=dispatch,
        details={"boost_count": boost_count},
    )
