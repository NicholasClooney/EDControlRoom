from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from time import monotonic, sleep
from typing import Callable

from edap.actions import ActionDispatchResult
from edap.multi_leg_haul import CargoTransfer, MultiLegHaulDefinition, RouteEndpoint, RouteStop, build_route_stops
from edap.routines._base import RoutineResult, SupportsHaulControls, SupportsPollEvents, _is_in_supercruise_event
from edap.routines.callbacks import AnnouncementCallback, ProgressCallback
from edap.routines.docking import _undock_until_undocked, _wait_for_clear_of_station, dock, station_refuel_menu
from edap.routines.escape import escape_mass_lock
from edap.routines.galaxy_map import set_gal_map_destination
from edap.routines.haul_two_way import (
    _read_cargo_json,
    _read_latest_journal_events,
    _read_market_station,
    _sellable_cargo,
)
from edap.routines.market import market_buy, market_sell
from edap.state import get_latest_journal_log, read_ship_state
from edap.tts import AnnouncementId


class Phase(Enum):
    SELL = auto()
    BUY = auto()
    UNDOCK = auto()
    DEPART_SYSTEM = auto()
    TRANSIT = auto()
    COMPLETE = auto()


class _TransitResumeState(Enum):
    NONE = auto()
    ARRIVED_IN_DESTINATION_SYSTEM = auto()
    POST_DROP_NEAR_STATION = auto()
    AWAITING_DOCKED = auto()


@dataclass
class _Ctx:
    controls: SupportsHaulControls
    watcher: SupportsPollEvents
    definition: MultiLegHaulDefinition
    stops: tuple[RouteStop, ...]
    journal_dir: Path
    market_path: Path
    step_delay_s: float
    max_hold_s: float
    market_buy_hold_seconds_per_ton: float
    dock_timeout_s: float
    request_timeout_s: float
    undock_timeout_s: float
    undock_no_track_timeout_s: float
    trade_timeout_s: float
    settle_s: float
    galaxy_map_settle_s: float
    supercruise_exit_settle_s: float
    boost_settle_s: float
    deny_retry_delay_s: float
    mass_lock_boost_delay_s: float
    post_sell_settle_s: float
    auto_hyperspace_engage: bool
    open_nav_panel_after_hyperspace_arrival: bool
    nav_panel_open_delay_s: float
    max_dock_retries: int
    market_critical_level_multiplier: float
    time_fn: Callable[[], float]
    sleeper: Callable[[float], None]
    progress_fn: ProgressCallback
    announce_fn: AnnouncementCallback


def _inventory_count(inventory: list[dict], commodity: str) -> int:
    total = 0
    commodity_lower = commodity.lower()
    for item in inventory:
        count = item.get("Count", 0)
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            continue
        if (
            str(item.get("Name", "")).lower() == commodity_lower
            or str(item.get("Name_Localised", "")).lower() == commodity_lower
        ):
            total += int(count)
    return total


def _has_all_cargo(inventory: list[dict], cargo: tuple[CargoTransfer, ...]) -> bool:
    if not cargo:
        return True
    return all(_inventory_count(inventory, item.commodity) >= item.amount for item in cargo)


def _has_any_cargo(inventory: list[dict], cargo: tuple[CargoTransfer, ...]) -> bool:
    return any(_inventory_count(inventory, item.commodity) > 0 for item in cargo)


def _detect_transit_resume_state(events: list[dict], destination: RouteEndpoint) -> _TransitResumeState:
    destination_station = destination.station.lower()
    destination_system = destination.system.lower()
    for event in reversed(events):
        evt_name = str(event.get("event", ""))
        if evt_name in {"DockingRequested", "DockingGranted"}:
            station_name = str(event.get("StationName", "")).lower()
            return _TransitResumeState.AWAITING_DOCKED if station_name == destination_station else _TransitResumeState.NONE
        if evt_name == "SupercruiseExit":
            body_type = str(event.get("BodyType", "")).lower()
            system_name = str(event.get("StarSystem", "")).lower()
            if body_type != "station":
                return _TransitResumeState.NONE
            return _TransitResumeState.POST_DROP_NEAR_STATION if not destination_system or system_name == destination_system else _TransitResumeState.NONE
        if evt_name in {"SupercruiseEntry", "FSDJump"}:
            system_name = str(event.get("StarSystem", "")).lower()
            return _TransitResumeState.ARRIVED_IN_DESTINATION_SYSTEM if not destination_system or system_name == destination_system else _TransitResumeState.NONE
        if evt_name == "Undocked":
            return _TransitResumeState.NONE
    return _TransitResumeState.NONE


def _wait_for_arrival_or_approach_event(
    watcher: SupportsPollEvents,
    *,
    deadline: float,
    time_fn: Callable[[], float],
) -> tuple[bool, list[dict[str, object]]]:
    approach_events = {"SupercruiseExit", "DockingRequested", "DockingGranted", "Docked"}
    while time_fn() <= deadline:
        batch = watcher.poll()
        for index, event in enumerate(batch):
            if _is_in_supercruise_event(event):
                return True, batch[index + 1:]
            if event.get("event") in approach_events:
                return False, batch[index:]
    return False, []


def _read_ship_position(journal_dir: Path) -> tuple[str, str, str]:
    ship_status = "unknown"
    current_station = ""
    current_system = ""
    log_path = get_latest_journal_log(journal_dir)
    if log_path is not None:
        try:
            state = read_ship_state(log_path)
        except Exception:
            state = None
        if state is not None:
            current_station = str(state.station or "")
            current_system = str(state.location or "")
            status = str(state.status or "")
            if status == "in_station":
                ship_status = "docked"
            elif status in {"in_space", "in_undocking", "starting_docking", "in_docking"}:
                ship_status = "normal_space"
            elif status in {"in_supercruise", "starting_hyperspace", "starting_supercruise"}:
                ship_status = "supercruise"
    if ship_status in {"docked", "unknown"}:
        market_station, market_system = _read_market_station(journal_dir)
        if not current_station and market_station:
            current_station = market_station
        if not current_system and market_system:
            current_system = market_system
        if current_station:
            ship_status = "docked"
    return ship_status, current_station, current_system


def _detect_start_state(ctx: _Ctx) -> tuple[int, Phase]:
    inventory = _read_cargo_json(ctx.journal_dir)
    ship_status, current_station, current_system = _read_ship_position(ctx.journal_dir)
    current_station_lower = current_station.lower()
    current_system_lower = current_system.lower()

    ctx.progress_fn(
        "Multi-leg phase detect: "
        f"status={ship_status}, station={current_station!r}, system={current_system!r}"
    )

    for stop in ctx.stops:
        if stop.endpoint.station and current_station_lower == stop.endpoint.station.lower():
            if _has_any_cargo(inventory, stop.inbound):
                return stop.index, Phase.SELL
            if stop.outbound and _has_all_cargo(inventory, stop.outbound):
                return stop.index, Phase.UNDOCK
            if stop.outbound:
                return stop.index, Phase.BUY
            return stop.index, Phase.COMPLETE

    for leg in ctx.definition.legs:
        if _has_all_cargo(inventory, leg.cargo):
            source_index = leg.index - 1
            if current_system_lower and current_system_lower == leg.source.system.lower():
                return source_index, Phase.DEPART_SYSTEM if ship_status == "normal_space" else Phase.UNDOCK
            return source_index, Phase.TRANSIT

    return 0, Phase.BUY if ctx.stops and ctx.stops[0].outbound else Phase.COMPLETE


def _engage_hyperspace_after_escape(ctx: _Ctx) -> None:
    if not ctx.auto_hyperspace_engage:
        return
    ctx.progress_fn("Mass lock cleared - engaging hyperspace...")
    ctx.announce_fn(AnnouncementId.STATION_CLEARED)
    ctx.controls.hyper_super_combination()


def _open_navigation_panel_after_arrival(ctx: _Ctx) -> None:
    if not ctx.open_nav_panel_after_hyperspace_arrival:
        return
    if ctx.nav_panel_open_delay_s > 0:
        ctx.progress_fn(f"Waiting {ctx.nav_panel_open_delay_s:.1f}s before opening navigation panel...")
        ctx.sleeper(ctx.nav_panel_open_delay_s)
    ctx.progress_fn("Hyperspace complete - opening left panel for navigation...")
    dispatch = ctx.controls.focus_left_panel()
    if dispatch.status != "ok":
        ctx.progress_fn(f"Warning: could not open left panel ({dispatch.reason or dispatch.status}); continuing")


def _run_sell(ctx: _Ctx, stop: RouteStop) -> RoutineResult:
    if not stop.inbound or not _sellable_cargo(_read_cargo_json(ctx.journal_dir)):
        return RoutineResult(action="market_sell", dispatch=ActionDispatchResult(action="market_sell", status="ok", reason="nothing to sell"))
    for cargo in stop.inbound:
        available = _inventory_count(_read_cargo_json(ctx.journal_dir), cargo.commodity)
        if available <= 0:
            ctx.progress_fn(f"{cargo.commodity} already absent at {stop.label} - skipping sell.")
            continue
        ctx.progress_fn(f"Selling {cargo.amount}t {cargo.commodity} at {stop.label}...")
        ctx.announce_fn(AnnouncementId.SELLING_CARGO, commodity_name=cargo.commodity)
        result = market_sell(
            ctx.controls,
            ctx.watcher,
            market_path=ctx.market_path,
            target=cargo.commodity,
            amount=str(min(available, cargo.amount)),
            step_delay_s=ctx.step_delay_s,
            max_hold_s=ctx.max_hold_s,
            buy_hold_seconds_per_ton=ctx.market_buy_hold_seconds_per_ton,
            trade_timeout_s=ctx.trade_timeout_s,
            time_fn=ctx.time_fn,
            sleeper=ctx.sleeper,
            progress_fn=ctx.progress_fn,
            announce_fn=ctx.announce_fn,
            critical_level_multiplier=ctx.market_critical_level_multiplier,
        )
        if result.dispatch.status != "ok":
            return result
        if ctx.post_sell_settle_s > 0:
            ctx.sleeper(ctx.post_sell_settle_s)
    return RoutineResult(action="market_sell", dispatch=ActionDispatchResult(action="market_sell", status="ok"))


def _run_buy(ctx: _Ctx, stop: RouteStop) -> RoutineResult:
    if not stop.outbound:
        return RoutineResult(action="market_buy", dispatch=ActionDispatchResult(action="market_buy", status="ok", reason="no outbound cargo"))
    for cargo in stop.outbound:
        already_loaded = _inventory_count(_read_cargo_json(ctx.journal_dir), cargo.commodity)
        remaining = max(0, cargo.amount - already_loaded)
        if remaining <= 0:
            ctx.progress_fn(f"{cargo.commodity} already loaded for departure from {stop.label} - skipping buy.")
            continue
        ctx.progress_fn(f"Buying {remaining}t {cargo.commodity} at {stop.label}...")
        ctx.announce_fn(AnnouncementId.BUYING_CARGO, commodity_name=cargo.commodity)
        result = market_buy(
            ctx.controls,
            ctx.watcher,
            market_path=ctx.market_path,
            target=cargo.commodity,
            amount=str(remaining),
            step_delay_s=ctx.step_delay_s,
            max_hold_s=ctx.max_hold_s,
            trade_timeout_s=ctx.trade_timeout_s,
            time_fn=ctx.time_fn,
            sleeper=ctx.sleeper,
            progress_fn=ctx.progress_fn,
            announce_fn=ctx.announce_fn,
            critical_level_multiplier=ctx.market_critical_level_multiplier,
        )
        if result.dispatch.status != "ok":
            return result
    return RoutineResult(action="market_buy", dispatch=ActionDispatchResult(action="market_buy", status="ok"))


def _undock_and_route(ctx: _Ctx, stop: RouteStop, next_stop: RouteStop) -> RoutineResult:
    ctx.progress_fn(f"Undocking from {stop.label}...")
    result, pending_events = _undock_until_undocked(
        ctx.controls,
        ctx.watcher,
        undock_timeout_s=ctx.undock_timeout_s,
        step_delay_s=ctx.step_delay_s,
        time_fn=ctx.time_fn,
        sleeper=ctx.sleeper,
        progress_fn=ctx.progress_fn,
    )
    if result.dispatch.status != "ok":
        return result
    if next_stop.endpoint.system:
        ctx.progress_fn(f"Setting galaxy map destination: {next_stop.endpoint.system}...")
        ctx.announce_fn(AnnouncementId.DESTINATION_SET, system_name=next_stop.endpoint.system)
        set_gal_map_destination(
            ctx.controls,
            destination=next_stop.endpoint.system,
            journal_dir=ctx.journal_dir,
            step_delay_s=ctx.step_delay_s,
            map_settle_s=ctx.galaxy_map_settle_s,
            sleeper=ctx.sleeper,
            progress_fn=ctx.progress_fn,
        )
    clear_result = _wait_for_clear_of_station(
        ctx.watcher,
        undocked_event=result.trigger_event,
        no_track_timeout_s=ctx.undock_no_track_timeout_s,
        time_fn=ctx.time_fn,
        progress_fn=ctx.progress_fn,
        pending_events=pending_events,
    )
    if clear_result.dispatch.status != "ok":
        ctx.progress_fn(f"Error: {clear_result.dispatch.reason}; haul aborted. You can resume with replay / ctrl-r.")
        ctx.announce_fn(AnnouncementId.HAUL_ABORTED)
        return clear_result
    escape_mass_lock(
        ctx.controls,
        journal_dir=ctx.journal_dir,
        step_delay_s=ctx.step_delay_s,
        boost_delay_s=ctx.mass_lock_boost_delay_s,
        sleeper=ctx.sleeper,
        progress_fn=ctx.progress_fn,
    )
    _engage_hyperspace_after_escape(ctx)
    return clear_result


def _depart_system(ctx: _Ctx, stop: RouteStop, next_stop: RouteStop) -> RoutineResult:
    ctx.progress_fn(f"Departing {stop.label} system in normal space...")
    if next_stop.endpoint.system:
        ctx.progress_fn(f"Setting galaxy map destination: {next_stop.endpoint.system}...")
        ctx.announce_fn(AnnouncementId.DESTINATION_SET, system_name=next_stop.endpoint.system)
        set_gal_map_destination(
            ctx.controls,
            destination=next_stop.endpoint.system,
            journal_dir=ctx.journal_dir,
            step_delay_s=ctx.step_delay_s,
            map_settle_s=ctx.galaxy_map_settle_s,
            sleeper=ctx.sleeper,
            progress_fn=ctx.progress_fn,
        )
    escape_mass_lock(
        ctx.controls,
        journal_dir=ctx.journal_dir,
        step_delay_s=ctx.step_delay_s,
        boost_delay_s=ctx.mass_lock_boost_delay_s,
        sleeper=ctx.sleeper,
        progress_fn=ctx.progress_fn,
    )
    _engage_hyperspace_after_escape(ctx)
    return RoutineResult(action="depart_system", dispatch=ActionDispatchResult(action="depart_system", status="ok"))


def _run_transit(ctx: _Ctx, next_stop: RouteStop) -> RoutineResult:
    recent_events = _read_latest_journal_events(ctx.journal_dir)
    resume_state = _detect_transit_resume_state(recent_events, next_stop.endpoint)
    pending_events: list[dict[str, object]] = []
    if resume_state == _TransitResumeState.AWAITING_DOCKED:
        ctx.progress_fn(f"Docking already in progress for {next_stop.label} - waiting for Docked.")
        return station_refuel_menu(
            ctx.controls,
            ctx.watcher,
            dock_timeout_s=ctx.dock_timeout_s,
            settle_s=ctx.settle_s,
            time_fn=ctx.time_fn,
            sleeper=ctx.sleeper,
            progress_fn=ctx.progress_fn,
        )
    if resume_state == _TransitResumeState.NONE:
        arrival_observed, pending_events = _wait_for_arrival_or_approach_event(
            ctx.watcher,
            deadline=ctx.time_fn() + ctx.dock_timeout_s,
            time_fn=ctx.time_fn,
        )
        if arrival_observed:
            ctx.progress_fn("Arrived in destination system")
            _open_navigation_panel_after_arrival(ctx)
    elif resume_state == _TransitResumeState.ARRIVED_IN_DESTINATION_SYSTEM:
        _open_navigation_panel_after_arrival(ctx)
    elif resume_state == _TransitResumeState.POST_DROP_NEAR_STATION:
        ctx.progress_fn(f"Already in normal space near {next_stop.label} - skipping drop wait.")

    return dock(
        ctx.controls,
        ctx.watcher,
        wait_for_supercruise_exit=resume_state != _TransitResumeState.POST_DROP_NEAR_STATION,
        auto_refuel=True,
        max_retries=ctx.max_dock_retries,
        request_timeout_s=ctx.request_timeout_s,
        dock_timeout_s=ctx.dock_timeout_s,
        settle_s=ctx.settle_s,
        step_delay_s=ctx.step_delay_s,
        supercruise_exit_settle_s=ctx.supercruise_exit_settle_s,
        boost_settle_s=ctx.boost_settle_s,
        deny_retry_delay_s=ctx.deny_retry_delay_s,
        time_fn=ctx.time_fn,
        sleeper=ctx.sleeper,
        progress_fn=ctx.progress_fn,
        pending_events=pending_events,
        announce_fn=ctx.announce_fn,
        announce_station_name=next_stop.endpoint.station,
    )


def multi_leg_haul(
    controls: SupportsHaulControls,
    watcher: SupportsPollEvents,
    *,
    definition: MultiLegHaulDefinition,
    journal_dir: Path,
    step_delay_s: float = 1.0,
    max_hold_s: float = 10.0,
    market_buy_hold_seconds_per_ton: float = 0.01,
    dock_timeout_s: float = 600.0,
    request_timeout_s: float = 20.0,
    undock_timeout_s: float = 30.0,
    undock_no_track_timeout_s: float = 600.0,
    trade_timeout_s: float = 30.0,
    settle_s: float = 2.0,
    galaxy_map_settle_s: float = 2.0,
    supercruise_exit_settle_s: float = 3.0,
    boost_settle_s: float = 3.0,
    deny_retry_delay_s: float = 5.0,
    mass_lock_boost_delay_s: float = 5.0,
    post_sell_settle_s: float = 2.0,
    auto_hyperspace_engage: bool = True,
    open_nav_panel_after_hyperspace_arrival: bool = True,
    nav_panel_open_delay_s: float = 3.0,
    max_dock_retries: int = 3,
    market_critical_level_multiplier: float = 10.0,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: ProgressCallback,
    announce_fn: AnnouncementCallback,
    stop_requested_fn: Callable[[], bool] | None = None,
) -> RoutineResult:
    stops = build_route_stops(definition)
    if not stops:
        raise ValueError("Multi-leg haul definition has no stops")
    ctx = _Ctx(
        controls=controls,
        watcher=watcher,
        definition=definition,
        stops=stops,
        journal_dir=journal_dir,
        market_path=journal_dir / "Market.json",
        step_delay_s=step_delay_s,
        max_hold_s=max_hold_s,
        market_buy_hold_seconds_per_ton=market_buy_hold_seconds_per_ton,
        dock_timeout_s=dock_timeout_s,
        request_timeout_s=request_timeout_s,
        undock_timeout_s=undock_timeout_s,
        undock_no_track_timeout_s=undock_no_track_timeout_s,
        trade_timeout_s=trade_timeout_s,
        settle_s=settle_s,
        galaxy_map_settle_s=galaxy_map_settle_s,
        supercruise_exit_settle_s=supercruise_exit_settle_s,
        boost_settle_s=boost_settle_s,
        deny_retry_delay_s=deny_retry_delay_s,
        mass_lock_boost_delay_s=mass_lock_boost_delay_s,
        post_sell_settle_s=post_sell_settle_s,
        auto_hyperspace_engage=auto_hyperspace_engage,
        open_nav_panel_after_hyperspace_arrival=open_nav_panel_after_hyperspace_arrival,
        nav_panel_open_delay_s=nav_panel_open_delay_s,
        max_dock_retries=max_dock_retries,
        market_critical_level_multiplier=market_critical_level_multiplier,
        time_fn=time_fn,
        sleeper=sleeper,
        progress_fn=progress_fn,
        announce_fn=announce_fn,
    )

    stop_index, phase = _detect_start_state(ctx)
    if phase != Phase.BUY or stop_index != 0:
        progress_fn(f"Resuming multi-leg haul from stop {stop_index + 1} phase {phase.name}")
    last_result = RoutineResult(action="multi_leg_haul", dispatch=ActionDispatchResult(action="multi_leg_haul", status="ok"))

    while stop_index < len(stops):
        stop = stops[stop_index]
        next_stop = stops[stop_index + 1] if stop_index + 1 < len(stops) else None
        if phase == Phase.COMPLETE:
            return last_result
        if stop_requested_fn is not None and stop_requested_fn() and phase in {Phase.BUY, Phase.UNDOCK, Phase.DEPART_SYSTEM}:
            progress_fn(f"Stop requested at {stop.label}; halting before departure.")
            return last_result
        if phase == Phase.SELL:
            last_result = _run_sell(ctx, stop)
            if last_result.dispatch.status != "ok":
                return last_result
            phase = Phase.BUY if stop.outbound else Phase.COMPLETE
            continue
        if phase == Phase.BUY:
            last_result = _run_buy(ctx, stop)
            if last_result.dispatch.status != "ok":
                return last_result
            phase = Phase.UNDOCK if next_stop is not None else Phase.COMPLETE
            continue
        if phase == Phase.UNDOCK:
            if next_stop is None:
                return last_result
            last_result = _undock_and_route(ctx, stop, next_stop)
            if last_result.dispatch.status != "ok":
                return last_result
            phase = Phase.TRANSIT
            continue
        if phase == Phase.DEPART_SYSTEM:
            if next_stop is None:
                return last_result
            last_result = _depart_system(ctx, stop, next_stop)
            if last_result.dispatch.status != "ok":
                return last_result
            phase = Phase.TRANSIT
            continue
        if phase == Phase.TRANSIT:
            if next_stop is None:
                return last_result
            last_result = _run_transit(ctx, next_stop)
            if last_result.dispatch.status != "ok":
                return last_result
            stop_index += 1
            phase = Phase.SELL
            continue
    return last_result
