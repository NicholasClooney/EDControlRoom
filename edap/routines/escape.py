from __future__ import annotations

from pathlib import Path
from time import sleep
from typing import Callable

from edap.actions import ActionDispatchResult
from edap.routines._base import RoutineResult, SupportsEscapeControls
from edap.status import read_status


def escape_mass_lock(
    controls: SupportsEscapeControls,
    *,
    journal_dir: Path,
    safety_delay_s: float = 0.0,
    boost_delay_s: float = 5.0,
    step_delay_s: float = 0.3,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: Callable[[str], None] | None = None,
) -> RoutineResult:
    if safety_delay_s < 0:
        raise ValueError("safety_delay_s must be non-negative")
    if boost_delay_s < 0:
        raise ValueError("boost_delay_s must be non-negative")
    if step_delay_s < 0:
        raise ValueError("step_delay_s must be non-negative")

    if progress_fn is not None and safety_delay_s > 0:
        progress_fn(f"Safety delay before mass-lock escape: waiting {safety_delay_s:.1f}s...")
    if safety_delay_s > 0:
        sleeper(safety_delay_s)

    if progress_fn is not None:
        progress_fn("Setting speed 100 to break auto-undock...")
    speed_result = controls.set_speed_full()
    if speed_result.status != "ok" and progress_fn is not None:
        progress_fn(f"Warning: SetSpeed100 dispatch failed: {speed_result.reason}")
    if step_delay_s > 0:
        sleeper(step_delay_s)

    boost_count = 0
    last_boost: ActionDispatchResult | None = None

    while True:
        status = read_status(journal_dir)
        if status is None or not status.flags.fsd_mass_locked:
            break
        if progress_fn is not None:
            progress_fn("FSD mass locked -- boosting away...")
        last_boost = controls.boost()
        if last_boost.status != "ok" and progress_fn is not None:
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
