from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
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


class SupportsUndockControls(Protocol):
    def ui_back(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Back action."""

    def head_look_reset(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the HeadLookReset action."""

    def ui_down(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Down action."""

    def ui_select(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Select action."""


class SupportsMarketControls(Protocol):
    def ui_select(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Select action."""

    def ui_down(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Down action."""

    def ui_right(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Right action."""

    def ui_back(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Back action."""


class SupportsDockingControls(SupportsStationMenuControls, SupportsSetSpeedZero, Protocol):
    def boost(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the BoostButton action."""

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

    def ui_left(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Left action."""


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
    progress_fn: Callable[[str], None] | None = None,
) -> RoutineResult:
    for event in events:
        if event.get("event") != "SupercruiseExit":
            continue

        if progress_fn is not None:
            system = event.get("StarSystem", "")
            progress_fn(f"SupercruiseExit: {system}" if system else "SupercruiseExit")
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
    progress_fn: Callable[[str], None] | None = None,
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
        if progress_fn is not None:
            progress_fn(f"Dispatching jump (attempt {attempt}/{max_retries})...")
        dispatch = controls.hyper_super_combination(hold_s=jump_hold_s)
        last_dispatch = dispatch
        if dispatch.status != "ok":
            return RoutineResult(
                action="HyperSuperCombination",
                dispatch=dispatch,
                details={"attempt": attempt, "max_retries": max_retries, "phase": "dispatch"},
            )

        if progress_fn is not None:
            progress_fn("Waiting for jump to start...")
        start_deadline = time_fn() + start_timeout_s
        start_event = _wait_for_event(
            watcher,
            predicate=_is_starting_hyperspace_event,
            deadline=start_deadline,
            time_fn=time_fn,
        )
        if start_event is None:
            if progress_fn is not None:
                progress_fn(f"Jump start timed out after {start_timeout_s:.0f}s, retrying...")
            continue

        if progress_fn is not None:
            progress_fn("Jump started, waiting for arrival...")
        completion_deadline = time_fn() + completion_timeout_s
        completion_event = _wait_for_event(
            watcher,
            predicate=_is_in_supercruise_event,
            deadline=completion_deadline,
            time_fn=time_fn,
        )
        if completion_event is None:
            if progress_fn is not None:
                progress_fn(f"Jump completion timed out after {completion_timeout_s:.0f}s, retrying...")
            continue

        if progress_fn is not None:
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


def _is_docking_response_event(event: dict[str, object]) -> bool:
    return event.get("event") in {"DockingRequested", "DockingGranted", "DockingDenied"}


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


def _is_docked_event(event: dict[str, object]) -> bool:
    return event.get("event") == "Docked"


def _is_undocked_event(event: dict[str, object]) -> bool:
    return event.get("event") == "Undocked"


def _market_localised(item: dict, key: str) -> str:
    return item.get(f"{key}_Localised") or item.get(key, "")


def _market_buy_list(items: list[dict]) -> list[tuple[str, str]]:
    rows = [
        (_market_localised(it, "Category"), _market_localised(it, "Name"))
        for it in items
        if it.get("Stock", 0) > 0
    ]
    return sorted(rows, key=lambda r: (r[0].lower(), r[1].lower()))


def _market_sell_list(items: list[dict]) -> list[tuple[str, str]]:
    # DemandBracket > 0 matches the in-game sell tab. Items with Demand=1 and
    # bracket=0 are placeholders the game does not display or accept.
    rows = [
        (_market_localised(it, "Category"), _market_localised(it, "Name"))
        for it in items
        if it.get("DemandBracket", 0) > 0
    ]
    return sorted(rows, key=lambda r: (r[0].lower(), r[1].lower()))


def _market_item_index(sorted_items: list[tuple[str, str]], target: str) -> int:
    t = target.lower()
    for i, (_, name) in enumerate(sorted_items):
        if name.lower() == t:
            return i
    sample = [name for _, name in sorted_items[:5]]
    suffix = "..." if len(sorted_items) > 5 else ""
    raise ValueError(f"'{target}' not found in market list (first items: {sample}{suffix})")


def _is_market_event(event: dict[str, object], event_type: str, target: str) -> bool:
    if event.get("event") != event_type:
        return False
    t = target.lower()
    return (
        t in str(event.get("Type_Localised", "")).lower()
        or t in str(event.get("Type", "")).lower()
    )


def _read_last_docked_event(journal_dir: Path) -> dict[str, object] | None:
    journal_files = sorted(journal_dir.glob("Journal.*.log"))
    if not journal_files:
        return None
    try:
        lines = journal_files[-1].read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("event") == "Docked":
                return event
        except json.JSONDecodeError:
            continue
    return None


def _market_error(action: str, reason: str) -> RoutineResult:
    return RoutineResult(
        action=action,
        dispatch=ActionDispatchResult(action=action, status="error", reason=reason),
    )


def market_buy(
    controls: SupportsMarketControls,
    watcher: SupportsPollEvents,
    *,
    market_path: Path,
    target: str,
    amount: int | str,
    step_delay_s: float = 1.0,
    max_hold_s: float = 10.0,
    trade_timeout_s: float = 30.0,
    skip_station_check: bool = False,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: Callable[[str], None] | None = None,
) -> RoutineResult:
    return _market_trade(
        controls, watcher,
        market_path=market_path, target=target, amount=amount, side="buy",
        step_delay_s=step_delay_s, max_hold_s=max_hold_s, trade_timeout_s=trade_timeout_s,
        skip_station_check=skip_station_check,
        time_fn=time_fn, sleeper=sleeper, progress_fn=progress_fn,
    )


def market_sell(
    controls: SupportsMarketControls,
    watcher: SupportsPollEvents,
    *,
    market_path: Path,
    target: str,
    amount: int | str,
    step_delay_s: float = 1.0,
    max_hold_s: float = 10.0,
    trade_timeout_s: float = 30.0,
    skip_station_check: bool = False,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: Callable[[str], None] | None = None,
) -> RoutineResult:
    return _market_trade(
        controls, watcher,
        market_path=market_path, target=target, amount=amount, side="sell",
        step_delay_s=step_delay_s, max_hold_s=max_hold_s, trade_timeout_s=trade_timeout_s,
        skip_station_check=skip_station_check,
        time_fn=time_fn, sleeper=sleeper, progress_fn=progress_fn,
    )


def _market_trade(
    controls: SupportsMarketControls,
    watcher: SupportsPollEvents,
    *,
    market_path: Path,
    target: str,
    amount: int | str,
    side: str,
    step_delay_s: float,
    max_hold_s: float,
    trade_timeout_s: float,
    skip_station_check: bool,
    time_fn: Callable[[], float],
    sleeper: Callable[[float], None],
    progress_fn: Callable[[str], None] | None,
) -> RoutineResult:
    event_type = "MarketBuy" if side == "buy" else "MarketSell"

    # Navigate to commodities market first -- the game writes Market.json when the screen opens
    if progress_fn is not None:
        progress_fn("Navigating to commodities market...")

    if progress_fn is not None:
        progress_fn("  UI_Select (enter station services)")
    dispatch = controls.ui_select()
    if dispatch.status != "ok":
        return RoutineResult(action=dispatch.action, dispatch=dispatch, details={"phase": "navigate_to_market"})
    # Station services UI takes a moment to populate after selection
    sleeper(7.0)

    for fn, label in [
        (controls.ui_down, "UI_Down (to commodities market)"),
        (controls.ui_select, "UI_Select (open market)"),
    ]:
        if progress_fn is not None:
            progress_fn(f"  {label}")
        dispatch = fn()
        if dispatch.status != "ok":
            return RoutineResult(action=dispatch.action, dispatch=dispatch, details={"phase": "navigate_to_market"})
        if step_delay_s > 0:
            sleeper(step_delay_s)

    # Verify Market.json matches the current docked station.
    # The game writes it when the market screen opens; retry up to 3 times if delayed.
    data: dict = {}
    if skip_station_check:
        if not market_path.exists():
            return _market_error(event_type, "Market.json not found")
        with market_path.open() as fh:
            data = json.load(fh)
        if progress_fn is not None:
            progress_fn("Station check skipped")
    else:
        _RETRIES = 3
        _RETRY_DELAY_S = 10.0
        for attempt in range(1, _RETRIES + 1):
            fail_reason: str | None = None
            if not market_path.exists():
                fail_reason = "Market.json not found"
            else:
                with market_path.open() as fh:
                    data = json.load(fh)
                docked = _read_last_docked_event(market_path.parent)
                if docked is None:
                    fail_reason = "no Docked event found in journal -- cannot verify current station"
                else:
                    market_id = data.get("MarketID")
                    docked_id = docked.get("MarketID")
                    if market_id and docked_id and market_id == docked_id:
                        pass  # confirmed match
                    elif data.get("StationName") and data.get("StationName") == docked.get("StationName"):
                        pass  # fallback name match
                    else:
                        fail_reason = (
                            f"Market.json is from {data.get('StationName', '?')!r} "
                            f"but last Docked event is {docked.get('StationName', '?')!r}"
                        )
            if fail_reason is None:
                break
            if attempt < _RETRIES:
                if progress_fn is not None:
                    progress_fn(f"Station check failed (attempt {attempt}/{_RETRIES}): {fail_reason}")
                    progress_fn(f"  Retrying in {_RETRY_DELAY_S:.0f}s...")
                sleeper(_RETRY_DELAY_S)
            else:
                return _market_error(event_type, f"Station check failed after {_RETRIES} attempts: {fail_reason}")

    items: list[dict] = data.get("Items", [])

    sorted_items = _market_buy_list(items) if side == "buy" else _market_sell_list(items)
    try:
        item_index = _market_item_index(sorted_items, target)
    except ValueError as exc:
        return _market_error(event_type, str(exc))

    if progress_fn is not None:
        progress_fn(f"Target '{target}' at position {item_index} in {side} list ({len(sorted_items)} items)")

    # For sell: navigate sidebar from BUY to SELL tab before entering the list
    if side == "sell":
        if progress_fn is not None:
            progress_fn("  UI_Down (BUY -> SELL tab)")
        dispatch = controls.ui_down()
        if dispatch.status != "ok":
            return RoutineResult(action="UI_Down", dispatch=dispatch, details={"phase": "navigate_to_sell_tab"})
        if step_delay_s > 0:
            sleeper(step_delay_s)

        if progress_fn is not None:
            progress_fn("  UI_Select (enter SELL tab)")
        dispatch = controls.ui_select()
        if dispatch.status != "ok":
            return RoutineResult(action="UI_Select", dispatch=dispatch, details={"phase": "navigate_to_sell_tab"})
        if step_delay_s > 0:
            sleeper(step_delay_s)

    # Enter the commodity list (cursor lands on the first item)
    if progress_fn is not None:
        progress_fn("  UI_Right (enter commodity list)")
    dispatch = controls.ui_right()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Right", dispatch=dispatch, details={"phase": "enter_list"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    # Navigate down to target item (category headers are non-navigable separators)
    if item_index > 0:
        if progress_fn is not None:
            progress_fn(f"  UI_Down x{item_index} (navigate to '{target}')")
        for _ in range(item_index):
            dispatch = controls.ui_down()
            if dispatch.status != "ok":
                return RoutineResult(action="UI_Down", dispatch=dispatch, details={"phase": "navigate_to_item"})
            if step_delay_s > 0:
                sleeper(step_delay_s)

    # Open the trade dialog for this item
    if progress_fn is not None:
        progress_fn(f"  UI_Select (open '{target}' dialog)")
    dispatch = controls.ui_select()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Select", dispatch=dispatch, details={"phase": "select_item"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    # Prime the watcher before setting quantity so the trade event is not missed
    watcher.poll()

    # Set quantity
    # Set quantity -- sell pre-fills with full cargo amount so no input needed
    if side == "buy":
        if amount == "MAX":
            if progress_fn is not None:
                progress_fn(f"  UI_Right hold {max_hold_s:.0f}s (fill to max)")
            qty_dispatch = controls.ui_right(hold_s=max_hold_s)
            if qty_dispatch.status != "ok":
                return RoutineResult(action="UI_Right", dispatch=qty_dispatch, details={"phase": "set_quantity"})
        else:
            qty = int(amount)
            if progress_fn is not None:
                progress_fn(f"  UI_Right x{qty} (set quantity to {qty})")
            qty_dispatch = None
            for _ in range(qty):
                qty_dispatch = controls.ui_right()
                if qty_dispatch.status != "ok":
                    return RoutineResult(action="UI_Right", dispatch=qty_dispatch, details={"phase": "set_quantity"})
                if step_delay_s > 0:
                    sleeper(step_delay_s)
            if qty_dispatch is None:
                return _market_error(event_type, "amount must be at least 1")
        if step_delay_s > 0:
            sleeper(step_delay_s)

    # Confirm trade
    confirm_label = "BUY" if side == "buy" else "SELL"
    if progress_fn is not None:
        progress_fn(f"  UI_Down (to {confirm_label} button)")
    dispatch = controls.ui_down()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Down", dispatch=dispatch, details={"phase": "confirm"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    if progress_fn is not None:
        progress_fn(f"  UI_Select (confirm {confirm_label})")
    trade_dispatch = controls.ui_select()
    if trade_dispatch.status != "ok":
        return RoutineResult(action="UI_Select", dispatch=trade_dispatch, details={"phase": "confirm"})

    # Wait for journal confirmation
    if progress_fn is not None:
        progress_fn(f"Waiting for {event_type} event (timeout {trade_timeout_s:.0f}s)...")
    trade_event = _wait_for_event(
        watcher,
        predicate=lambda e: _is_market_event(e, event_type, target),
        deadline=time_fn() + trade_timeout_s,
        time_fn=time_fn,
    )
    if trade_event is None:
        return RoutineResult(
            action=event_type,
            dispatch=ActionDispatchResult(
                action=event_type,
                status="error",
                reason=f"{event_type} for '{target}' not observed within {trade_timeout_s:.0f}s",
            ),
            details={"phase": "wait_for_event"},
        )

    if progress_fn is not None:
        count = trade_event.get("Count", "?")
        cr_key = "TotalCost" if side == "buy" else "TotalSale"
        cr_val = trade_event.get(cr_key, "?")
        progress_fn(f"{event_type}: {count}x {target}, {cr_val} CR total")

    # Return to station menu
    if progress_fn is not None:
        progress_fn("  UI_Back x2 (return to station menu)")
    controls.ui_back(repeat=2)

    return RoutineResult(
        action=event_type,
        dispatch=trade_dispatch,
        trigger_event=trade_event,
        details={"target": target, "amount": str(amount), "side": side},
    )


class SupportsGalaxyMapControls(Protocol):
    def galaxy_map_open(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the GalaxyMapOpen action."""

    def ui_up(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Up action."""

    def ui_down(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Down action."""

    def ui_select(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Select action."""

    def ui_right(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Right action."""

    def cam_zoom_in(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the CamZoomIn action."""

    def type_text(self, text: str) -> None:
        """Type a string of text character by character."""


class SupportsHaulControls(SupportsDockingControls, SupportsUndockControls, SupportsMarketControls, Protocol):
    """Combined protocol for all controls needed in the haul loop."""


def _read_cargo_json(journal_dir: Path) -> list[dict]:
    cargo_path = journal_dir / "Cargo.json"
    try:
        with cargo_path.open() as fh:
            data = json.load(fh)
        return data.get("Inventory", [])
    except (OSError, json.JSONDecodeError):
        return []


def _sellable_cargo(inventory: list[dict]) -> list[dict]:
    return [
        item for item in inventory
        if item.get("Count", 0) > 0
        and item.get("Stolen", 0) == 0
        and "MissionID" not in item
    ]


def haul_loop(
    controls: SupportsHaulControls,
    watcher: SupportsPollEvents,
    *,
    journal_dir: Path,
    commodity: str,
    sell_station: str = "",
    buy_station: str = "",
    iterations: int = 0,
    step_delay_s: float = 1.0,
    max_hold_s: float = 10.0,
    dock_timeout_s: float = 120.0,
    request_timeout_s: float = 20.0,
    undock_timeout_s: float = 30.0,
    trade_timeout_s: float = 30.0,
    settle_s: float = 2.0,
    boost_settle_s: float = 3.0,
    deny_retry_delay_s: float = 5.0,
    max_dock_retries: int = 3,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: Callable[[str], None] | None = None,
) -> RoutineResult:
    """Community hauling loop: sell all cargo, undock, dock buy station, buy commodity, undock, dock sell station, refuel, repeat."""
    if iterations < 0:
        raise ValueError("iterations must be non-negative (0 = infinite)")

    market_path = journal_dir / "Market.json"
    sell_label = f" ({sell_station})" if sell_station else ""
    buy_label = f" ({buy_station})" if buy_station else ""

    iteration = 0
    last_result: RoutineResult | None = None

    while iterations == 0 or iteration < iterations:
        iteration += 1
        if progress_fn is not None:
            iter_label = f" of {iterations}" if iterations > 0 else ""
            progress_fn(f"=== Haul loop iteration {iteration}{iter_label} ===")

        # Phase 1: sell all cargo at sell station
        cargo = _read_cargo_json(journal_dir)
        sellable = _sellable_cargo(cargo)

        if not sellable:
            if progress_fn is not None:
                progress_fn(f"No sellable cargo{sell_label} -- skipping sell phase")
        else:
            if progress_fn is not None:
                names = ", ".join(item.get("Name_Localised") or item.get("Name", "?") for item in sellable)
                progress_fn(f"Selling cargo{sell_label}: {names}")

            for item in sellable:
                name = item.get("Name_Localised") or item.get("Name", "?")
                if progress_fn is not None:
                    progress_fn(f"  Selling {name} (MAX)...")
                result = market_sell(
                    controls, watcher,
                    market_path=market_path,
                    target=name,
                    amount="MAX",
                    step_delay_s=step_delay_s,
                    max_hold_s=max_hold_s,
                    trade_timeout_s=trade_timeout_s,
                    time_fn=time_fn,
                    sleeper=sleeper,
                    progress_fn=progress_fn,
                )
                last_result = result
                if result.dispatch.status != "ok":
                    if progress_fn is not None:
                        progress_fn(f"  Skipping {name}: {result.dispatch.reason}")

        # Phase 2: undock from sell station
        if progress_fn is not None:
            progress_fn(f"Undocking from sell station{sell_label}...")
        result = undock(
            controls, watcher,
            undock_timeout_s=undock_timeout_s,
            step_delay_s=step_delay_s,
            time_fn=time_fn,
            sleeper=sleeper,
            progress_fn=progress_fn,
        )
        last_result = result
        if result.dispatch.status != "ok":
            if progress_fn is not None:
                progress_fn(f"Undock from sell station failed: {result.dispatch.reason}")
            return result

        # Phase 3: wait for supercruise exit + dock at buy station
        if progress_fn is not None:
            progress_fn(f"Waiting for drop near buy station{buy_label}...")
        result = dock(
            controls, watcher,
            wait_for_supercruise_exit=True,
            auto_refuel=False,
            max_retries=max_dock_retries,
            request_timeout_s=request_timeout_s,
            dock_timeout_s=dock_timeout_s,
            settle_s=settle_s,
            step_delay_s=step_delay_s,
            boost_settle_s=boost_settle_s,
            deny_retry_delay_s=deny_retry_delay_s,
            time_fn=time_fn,
            sleeper=sleeper,
            progress_fn=progress_fn,
        )
        last_result = result
        if result.dispatch.status != "ok":
            if progress_fn is not None:
                progress_fn(f"Dock at buy station{buy_label} failed: {result.dispatch.reason}")
            return result

        # Phase 4: buy commodity at buy station
        if progress_fn is not None:
            progress_fn(f"Buying {commodity} (MAX){buy_label}...")
        result = market_buy(
            controls, watcher,
            market_path=market_path,
            target=commodity,
            amount="MAX",
            step_delay_s=step_delay_s,
            max_hold_s=max_hold_s,
            trade_timeout_s=trade_timeout_s,
            time_fn=time_fn,
            sleeper=sleeper,
            progress_fn=progress_fn,
        )
        last_result = result
        if result.dispatch.status != "ok":
            if progress_fn is not None:
                progress_fn(f"Buy {commodity} failed: {result.dispatch.reason}")
            return result

        # Phase 5: undock from buy station
        if progress_fn is not None:
            progress_fn(f"Undocking from buy station{buy_label}...")
        result = undock(
            controls, watcher,
            undock_timeout_s=undock_timeout_s,
            step_delay_s=step_delay_s,
            time_fn=time_fn,
            sleeper=sleeper,
            progress_fn=progress_fn,
        )
        last_result = result
        if result.dispatch.status != "ok":
            if progress_fn is not None:
                progress_fn(f"Undock from buy station failed: {result.dispatch.reason}")
            return result

        # Phase 6: wait for supercruise exit + dock at sell station + auto-refuel
        if progress_fn is not None:
            progress_fn(f"Waiting for drop near sell station{sell_label}...")
        result = dock(
            controls, watcher,
            wait_for_supercruise_exit=True,
            auto_refuel=True,
            max_retries=max_dock_retries,
            request_timeout_s=request_timeout_s,
            dock_timeout_s=dock_timeout_s,
            settle_s=settle_s,
            step_delay_s=step_delay_s,
            boost_settle_s=boost_settle_s,
            deny_retry_delay_s=deny_retry_delay_s,
            time_fn=time_fn,
            sleeper=sleeper,
            progress_fn=progress_fn,
        )
        last_result = result
        if result.dispatch.status != "ok":
            if progress_fn is not None:
                progress_fn(f"Dock at sell station{sell_label} failed: {result.dispatch.reason}")
            return result

        if progress_fn is not None:
            progress_fn(f"Iteration {iteration} complete.")

    assert last_result is not None
    return last_result


def _read_navroute_destination(journal_dir: Path) -> str | None:
    navroute_path = journal_dir / "NavRoute.json"
    try:
        with navroute_path.open() as fh:
            data = json.load(fh)
        route = data.get("Route", [])
        if route:
            return str(route[-1].get("StarSystem", ""))
        return None
    except (OSError, json.JSONDecodeError):
        return None


def set_gal_map_destination(
    controls: SupportsGalaxyMapControls,
    *,
    destination: str,
    journal_dir: Path,
    open_check_fn: Callable[[], bool] | None = None,
    open_timeout_s: float = 10.0,
    open_settle_s: float = 3.0,
    search_settle_s: float = 2.0,
    plot_timeout_s: float = 15.0,
    step_delay_s: float = 0.5,
    zoom_select_hold_s: float = 0.75,
    max_results: int = 5,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: Callable[[str], None] | None = None,
) -> RoutineResult:
    """Odyssey galaxy map flow: open map, search by name, plot route, verify NavRoute."""
    if max_results < 1:
        raise ValueError("max_results must be at least 1")

    def _err(action: str, reason: str, phase: str, **extra: object) -> RoutineResult:
        return RoutineResult(
            action=action,
            dispatch=ActionDispatchResult(action=action, status="error", reason=reason),
            details={"phase": phase, **extra},
        )

    # Step 1: open the galaxy map
    if progress_fn is not None:
        progress_fn("Opening galaxy map...")
    dispatch = controls.galaxy_map_open()
    if dispatch.status != "ok":
        return RoutineResult(action="GalaxyMapOpen", dispatch=dispatch, details={"phase": "open"})

    # Step 2: wait for map to be ready (OCR check or fixed settle)
    if open_check_fn is not None:
        if progress_fn is not None:
            progress_fn("Waiting for galaxy map (CARTOGRAPHICS check)...")
        deadline = time_fn() + open_timeout_s
        while time_fn() < deadline:
            if open_check_fn():
                break
            sleeper(0.5)
        else:
            if progress_fn is not None:
                progress_fn("Galaxy map open check timed out, proceeding anyway...")
    elif open_settle_s > 0:
        sleeper(open_settle_s)

    # Step 3: navigate to search field (UI_Up + UI_Select)
    if progress_fn is not None:
        progress_fn("Navigating to search field...")
    dispatch = controls.ui_up()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Up", dispatch=dispatch, details={"phase": "navigate_to_search"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    dispatch = controls.ui_select()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Select", dispatch=dispatch, details={"phase": "navigate_to_search"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    # Step 4: type destination + Enter to commit search
    if progress_fn is not None:
        progress_fn(f"Typing destination: {destination!r}")
    controls.type_text(destination)
    if step_delay_s > 0:
        sleeper(step_delay_s)

    if progress_fn is not None:
        progress_fn("Committing search (Enter)...")
    controls.type_text("\n")
    if search_settle_s > 0:
        sleeper(search_settle_s)

    # Steps 5-6: select results and verify, retrying on mismatch
    last_plot_dispatch: ActionDispatchResult | None = None
    for attempt in range(1, max_results + 1):
        if attempt == 1:
            if progress_fn is not None:
                progress_fn("Selecting first search result...")
            dispatch = controls.ui_right()
            if dispatch.status != "ok":
                return RoutineResult(action="UI_Right", dispatch=dispatch, details={"phase": "select_result", "attempt": attempt})
            if step_delay_s > 0:
                sleeper(step_delay_s)

            dispatch = controls.ui_select()
            if dispatch.status != "ok":
                return RoutineResult(action="UI_Select", dispatch=dispatch, details={"phase": "select_result", "attempt": attempt})
            if step_delay_s > 0:
                sleeper(step_delay_s)
        else:
            if progress_fn is not None:
                progress_fn(f"Trying next result (attempt {attempt}/{max_results})...")
            dispatch = controls.ui_down()
            if dispatch.status != "ok":
                return RoutineResult(action="UI_Down", dispatch=dispatch, details={"phase": "next_result", "attempt": attempt})
            if step_delay_s > 0:
                sleeper(step_delay_s)

            dispatch = controls.ui_select()
            if dispatch.status != "ok":
                return RoutineResult(action="UI_Select", dispatch=dispatch, details={"phase": "next_result", "attempt": attempt})
            if step_delay_s > 0:
                sleeper(step_delay_s)

        # CamZoomIn (Z) + UI_Select held to plot the route
        if progress_fn is not None:
            progress_fn("Plotting route (CamZoomIn + UI_Select)...")
        dispatch = controls.cam_zoom_in()
        if dispatch.status != "ok":
            return RoutineResult(action="CamZoomIn", dispatch=dispatch, details={"phase": "plot_route", "attempt": attempt})
        if step_delay_s > 0:
            sleeper(step_delay_s)

        last_plot_dispatch = controls.ui_select(hold_s=zoom_select_hold_s)
        if last_plot_dispatch.status != "ok":
            return RoutineResult(action="UI_Select", dispatch=last_plot_dispatch, details={"phase": "plot_route", "attempt": attempt})

        # Poll NavRoute.json until destination matches or timeout
        if progress_fn is not None:
            progress_fn(f"Waiting for route to {destination!r} (up to {plot_timeout_s:.0f}s)...")
        deadline = time_fn() + plot_timeout_s
        actual: str | None = None
        while time_fn() < deadline:
            actual = _read_navroute_destination(journal_dir)
            if actual is not None and actual.lower() == destination.lower():
                break
            sleeper(0.5)

        if actual is not None and actual.lower() == destination.lower():
            if progress_fn is not None:
                progress_fn(f"Route set to {actual!r}")
            if progress_fn is not None:
                progress_fn("Closing galaxy map...")
            controls.galaxy_map_open()
            assert last_plot_dispatch is not None
            return RoutineResult(
                action="GalaxyMapOpen",
                dispatch=last_plot_dispatch,
                details={"destination": destination, "actual": actual, "attempts": attempt},
            )

        if progress_fn is not None:
            got = actual or "unknown"
            progress_fn(f"Route not confirmed after {plot_timeout_s:.0f}s (got {got!r}), trying next result...")

    # Exhausted all results — close map and return error
    controls.galaxy_map_open()
    return _err("GalaxyMapOpen", f"no matching result after {max_results} attempts", "verify_route", destination=destination)


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
