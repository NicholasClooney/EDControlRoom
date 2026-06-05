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


class SupportsStationMenuControls(Protocol):
    def ui_up(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Up action."""

    def ui_select(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Select action."""

    def ui_down(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Down action."""


class SupportsDockingControls(SupportsStationMenuControls, SupportsSetSpeedZero, Protocol):
    def focus_left_panel(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the FocusLeftPanel action."""

    def ui_back(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Back action."""

    def cycle_next_panel(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the CycleNextPanel action."""

    def cycle_previous_panel(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the CyclePreviousPanel action."""

    def ui_right(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Right action."""


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


def _is_supercruise_exit_event(event: dict[str, object]) -> bool:
    return event.get("event") == "SupercruiseExit"


def _is_docking_started_event(event: dict[str, object]) -> bool:
    return event.get("event") in {"DockingRequested", "DockingGranted"}


def station_refuel_menu(
    controls: SupportsStationMenuControls,
    watcher: SupportsPollEvents,
    *,
    dock_timeout_s: float = 120.0,
    settle_s: float = 2.0,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
) -> RoutineResult:
    if dock_timeout_s < 0:
        raise ValueError("dock_timeout_s must be non-negative")
    if settle_s < 0:
        raise ValueError("settle_s must be non-negative")

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
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
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

    supercruise_exit_event: dict[str, object] | None = None
    if wait_for_supercruise_exit:
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
        request_dispatch = docking_request_sequence(controls, step_delay_s=step_delay_s, sleeper=sleeper)
        if request_dispatch.status != "ok":
            return RoutineResult(
                action=request_dispatch.action,
                dispatch=request_dispatch,
                trigger_event=supercruise_exit_event,
                details={"phase": "dispatch", "attempt": attempt, "max_retries": max_retries},
            )

        request_event = _wait_for_event(
            watcher,
            predicate=_is_docking_started_event,
            deadline=time_fn() + request_timeout_s,
            time_fn=time_fn,
        )
        if request_event is None:
            continue

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
        controls.ui_right,
        controls.ui_select,
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


def _is_docked_event(event: dict[str, object]) -> bool:
    return event.get("event") == "Docked"
