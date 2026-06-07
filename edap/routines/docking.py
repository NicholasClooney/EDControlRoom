from __future__ import annotations

from time import monotonic, sleep
from typing import Callable

from edap.actions import ActionDispatchResult
from edap.routines._base import (
    RoutineResult,
    SupportsDockingControls,
    SupportsPollEvents,
    SupportsStationMenuControls,
    SupportsUndockControls,
    _is_docked_event,
    _is_docking_response_event,
    _is_supercruise_exit_event,
    _is_undocked_event,
    _wait_for_event,
)


def station_refuel_menu_sequence(
    controls: SupportsStationMenuControls,
    *,
    settle_s: float = 0.5,
    sleeper: Callable[[float], None] = sleep,
    trigger_event: dict[str, object] | None = None,
    pre_wait_s: float = 0.0,
) -> RoutineResult:
    if settle_s < 0:
        raise ValueError("settle_s must be non-negative")

    up_dispatch = controls.ui_up()
    if up_dispatch.status != "ok":
        return RoutineResult(
            action="UI_Up",
            dispatch=up_dispatch,
            details={"phase": "ui_up"},
        )

    if settle_s > 0:
        sleeper(settle_s)

    select_dispatch = controls.ui_select()
    if select_dispatch.status != "ok":
        return RoutineResult(
            action="UI_Select",
            dispatch=select_dispatch,
            details={"phase": "ui_select"},
        )

    if settle_s > 0:
        sleeper(settle_s)

    down_dispatch = controls.ui_down()
    return RoutineResult(
        action="UI_Down",
        dispatch=down_dispatch,
        wait_s=pre_wait_s + (settle_s * 2),
        trigger_event=trigger_event,
        details={
            "phase": "ui_down",
            "sequence": [
                up_dispatch.to_dict(),
                select_dispatch.to_dict(),
                down_dispatch.to_dict(),
            ],
        },
    )


def docking_request_sequence(
    controls: SupportsDockingControls,
    *,
    step_delay_s: float = 0.3,
    post_request_delay_s: float = 1.0,
    sleeper: Callable[[float], None] = sleep,
) -> ActionDispatchResult:
    if step_delay_s < 0:
        raise ValueError("step_delay_s must be non-negative")
    if post_request_delay_s < 0:
        raise ValueError("post_request_delay_s must be non-negative")

    steps = [
        lambda: controls.ui_back(repeat=10),
        controls.focus_left_panel,
        controls.cycle_next_panel,
        controls.cycle_next_panel,
        controls.ui_left,
        controls.ui_left,
        controls.ui_left,
        controls.ui_right,
        controls.ui_select,
        controls.ui_left,
        controls.cycle_previous_panel,
        controls.cycle_previous_panel,
        controls.ui_back,
    ]
    last_dispatch: ActionDispatchResult | None = None
    for step in steps:
        dispatch = step()
        if dispatch.status != "ok":
            return dispatch
        last_dispatch = dispatch
        if step_delay_s > 0:
            sleeper(step_delay_s)
    if post_request_delay_s > 0:
        sleeper(post_request_delay_s)
    assert last_dispatch is not None
    return last_dispatch


def station_refuel_menu(
    controls: SupportsStationMenuControls,
    watcher: SupportsPollEvents,
    *,
    dock_timeout_s: float = 120.0,
    settle_s: float = 2.0,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: Callable[[str], None] | None = None,
) -> RoutineResult:
    if dock_timeout_s < 0:
        raise ValueError("dock_timeout_s must be non-negative")
    if settle_s < 0:
        raise ValueError("settle_s must be non-negative")

    if progress_fn is not None:
        progress_fn("Waiting for Docked...")
    docked_event = _wait_for_event(
        watcher,
        predicate=_is_docked_event,
        deadline=time_fn() + dock_timeout_s,
        time_fn=time_fn,
    )
    if docked_event is None:
        return RoutineResult(
            action="Docked",
            dispatch=ActionDispatchResult(
                action="Docked",
                status="error",
                reason="docked event was not observed before timeout",
            ),
            details={"phase": "wait_for_docked", "dock_timeout_s": dock_timeout_s},
        )

    if progress_fn is not None:
        station = docked_event.get("StationName", "")
        progress_fn(f"Docked: {station}" if station else "Docked")
    if settle_s > 0:
        sleeper(settle_s)

    return station_refuel_menu_sequence(
        controls,
        settle_s=0.5,
        sleeper=sleeper,
        trigger_event=docked_event,
        pre_wait_s=settle_s,
    )


def dock(
    controls: SupportsDockingControls,
    watcher: SupportsPollEvents,
    *,
    wait_for_supercruise_exit: bool = True,
    auto_refuel: bool = False,
    max_retries: int = 3,
    request_timeout_s: float = 20.0,
    dock_timeout_s: float = 120.0,
    settle_s: float = 2.0,
    step_delay_s: float = 0.3,
    boost_settle_s: float = 3.0,
    deny_retry_delay_s: float = 5.0,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: Callable[[str], None] | None = None,
) -> RoutineResult:
    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")
    if request_timeout_s < 0:
        raise ValueError("request_timeout_s must be non-negative")
    if dock_timeout_s < 0:
        raise ValueError("dock_timeout_s must be non-negative")
    if settle_s < 0:
        raise ValueError("settle_s must be non-negative")
    if step_delay_s < 0:
        raise ValueError("step_delay_s must be non-negative")
    if boost_settle_s < 0:
        raise ValueError("boost_settle_s must be non-negative")
    if deny_retry_delay_s < 0:
        raise ValueError("deny_retry_delay_s must be non-negative")

    supercruise_exit_event: dict[str, object] | None = None
    if wait_for_supercruise_exit:
        if progress_fn is not None:
            progress_fn("Waiting for SupercruiseExit...")
        supercruise_exit_event = _wait_for_event(
            watcher,
            predicate=_is_supercruise_exit_event,
            deadline=time_fn() + dock_timeout_s,
            time_fn=time_fn,
        )
        if supercruise_exit_event is None:
            return RoutineResult(
                action="SupercruiseExit",
                dispatch=ActionDispatchResult(
                    action="SupercruiseExit",
                    status="error",
                    reason="supercruise exit was not observed before timeout",
                ),
                details={"phase": "wait_for_supercruise_exit", "dock_timeout_s": dock_timeout_s},
            )
        if progress_fn is not None:
            system = supercruise_exit_event.get("StarSystem", "")
            progress_fn(f"SupercruiseExit: {system}" if system else "SupercruiseExit")
        if progress_fn is not None:
            progress_fn("Boosting toward station...")
        controls.boost()
        if boost_settle_s > 0:
            sleeper(boost_settle_s)

    # Prime the watcher offset before the first request so that journal events
    # written during docking_request_sequence are not missed. Without this,
    # the first poll() sets the offset to end-of-file *after* the sequence
    # completes, skipping DockingRequested/DockingGranted silently.
    # When wait_for_supercruise_exit=True the supercruise _wait_for_event loop
    # already primed the offset; this call is then a fast no-op.
    watcher.poll()

    request_event: dict[str, object] | None = None
    zero_dispatch: ActionDispatchResult | None = None
    for attempt in range(1, max_retries + 1):
        if progress_fn is not None:
            progress_fn(f"Sending dock request (attempt {attempt}/{max_retries})...")
        request_dispatch = docking_request_sequence(controls, step_delay_s=step_delay_s, sleeper=sleeper)
        if request_dispatch.status != "ok":
            return RoutineResult(
                action=request_dispatch.action,
                dispatch=request_dispatch,
                trigger_event=supercruise_exit_event,
                details={"phase": "dispatch", "attempt": attempt, "max_retries": max_retries},
            )

        if progress_fn is not None:
            progress_fn("Waiting for docking response...")
        response_event = _wait_for_event(
            watcher,
            predicate=_is_docking_response_event,
            deadline=time_fn() + request_timeout_s,
            time_fn=time_fn,
        )
        if response_event is None:
            if progress_fn is not None:
                progress_fn("No docking response, retrying...")
            continue

        if response_event.get("event") == "DockingDenied":
            if progress_fn is not None:
                reason = response_event.get("Reason", "")
                progress_fn(f"DockingDenied: {reason} -- retrying in {deny_retry_delay_s:.0f}s...")
            sleeper(deny_retry_delay_s)
            continue

        request_event = response_event
        if progress_fn is not None:
            evt = request_event.get("event", "")
            station = request_event.get("StationName", "")
            progress_fn(f"{evt}: {station}" if station else str(evt))
        zero_dispatch = controls.set_speed_zero(repeat=2)
        break

    if request_event is None:
        return RoutineResult(
            action="DockingRequested",
            dispatch=ActionDispatchResult(
                action="DockingRequested",
                status="error",
                reason="docking request/grant was not observed before retry budget was exhausted",
            ),
            trigger_event=supercruise_exit_event,
            details={"phase": "wait_for_docking_request", "attempts": max_retries},
        )

    if progress_fn is not None:
        progress_fn("Waiting for Docked...")
    docked_event = _wait_for_event(
        watcher,
        predicate=_is_docked_event,
        deadline=time_fn() + dock_timeout_s,
        time_fn=time_fn,
    )
    if docked_event is None:
        return RoutineResult(
            action="Docked",
            dispatch=ActionDispatchResult(
                action="Docked",
                status="error",
                reason="docked event was not observed before timeout",
            ),
            trigger_event=request_event,
            details={"phase": "wait_for_docked", "dock_timeout_s": dock_timeout_s},
        )

    if progress_fn is not None:
        station = docked_event.get("StationName", "")
        progress_fn(f"Docked: {station}" if station else "Docked")

    details = {
        "supercruise_exit_event": supercruise_exit_event,
        "request_event": request_event,
        "docked_event": docked_event,
        "auto_refuel": auto_refuel,
    }
    if not auto_refuel:
        assert zero_dispatch is not None
        return RoutineResult(
            action="SetSpeedZero",
            dispatch=zero_dispatch,
            trigger_event=docked_event,
            details=details,
        )

    if settle_s > 0:
        sleeper(settle_s)

    refuel_result = station_refuel_menu_sequence(
        controls,
        settle_s=0.5,
        sleeper=sleeper,
        trigger_event=docked_event,
        pre_wait_s=settle_s,
    )
    return RoutineResult(
        action=refuel_result.action,
        dispatch=refuel_result.dispatch,
        wait_s=refuel_result.wait_s,
        trigger_event=refuel_result.trigger_event,
        details={
            **details,
            "followup_action": "station_refuel_menu",
            "followup_details": refuel_result.details,
        },
    )


def undock(
    controls: SupportsUndockControls,
    watcher: SupportsPollEvents,
    *,
    undock_timeout_s: float = 30.0,
    step_delay_s: float = 0.3,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: Callable[[str], None] | None = None,
) -> RoutineResult:
    if undock_timeout_s < 0:
        raise ValueError("undock_timeout_s must be non-negative")
    if step_delay_s < 0:
        raise ValueError("step_delay_s must be non-negative")

    if progress_fn is not None:
        progress_fn("Resetting UI state...")
    dispatch = controls.ui_back(repeat=10)
    if dispatch.status != "ok":
        return RoutineResult(
            action="UI_Back",
            dispatch=dispatch,
            details={"phase": "reset"},
        )
    if step_delay_s > 0:
        sleeper(step_delay_s)

    dispatch = controls.head_look_reset()
    if dispatch.status != "ok":
        return RoutineResult(
            action="HeadLookReset",
            dispatch=dispatch,
            details={"phase": "reset"},
        )
    if step_delay_s > 0:
        sleeper(step_delay_s)

    if progress_fn is not None:
        progress_fn("Navigating to Launch...")
    dispatch = controls.ui_down()
    if dispatch.status != "ok":
        return RoutineResult(
            action="UI_Down",
            dispatch=dispatch,
            details={"phase": "navigate"},
        )
    if step_delay_s > 0:
        sleeper(step_delay_s)

    launch_dispatch = controls.ui_select()
    if launch_dispatch.status != "ok":
        return RoutineResult(
            action="UI_Select",
            dispatch=launch_dispatch,
            details={"phase": "launch"},
        )

    # Prime the watcher before waiting so events written during the menu walk
    # are not missed on the first poll.
    watcher.poll()

    if progress_fn is not None:
        progress_fn(f"Waiting for Undocked (timeout {undock_timeout_s:.0f}s)...")
    undocked_event = _wait_for_event(
        watcher,
        predicate=_is_undocked_event,
        deadline=time_fn() + undock_timeout_s,
        time_fn=time_fn,
    )
    if undocked_event is None:
        return RoutineResult(
            action="UI_Select",
            dispatch=ActionDispatchResult(
                action="UI_Select",
                status="error",
                reason=f"Undocked event was not observed within {undock_timeout_s:.0f}s — menu walk may have missed Launch",
            ),
            details={"phase": "wait_for_undocked", "undock_timeout_s": undock_timeout_s},
        )

    if progress_fn is not None:
        station = undocked_event.get("StationName", "")
        progress_fn(f"Undocked: {station}" if station else "Undocked")
    return RoutineResult(
        action="Undocked",
        dispatch=launch_dispatch,
        trigger_event=undocked_event,
        details={"phase": "complete"},
    )
