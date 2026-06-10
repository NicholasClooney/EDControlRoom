from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from time import monotonic, sleep
from typing import Callable

from edap.actions import ActionDispatchResult
from edap.routines._base import (
    RoutineResult,
    SupportsHaulControls,
    SupportsPollEvents,
    _is_in_supercruise_event,
)
from edap.routines._callbacks import AnnouncementCallback, ProgressCallback
from edap.routines.docking import _undock_until_undocked, _wait_for_clear_of_station, dock, station_refuel_menu
from edap.routines.escape import escape_mass_lock
from edap.routines.galaxy_map import set_gal_map_destination
from edap.routines.market import market_buy, market_sell
from edap.state import get_latest_journal_log, read_ship_state
from edap.tts import AnnouncementId


def _read_cargo_json(journal_dir: Path) -> list[dict]:
    cargo_path = journal_dir / "Cargo.json"
    try:
        with cargo_path.open() as fh:
            data = json.load(fh)
        return data.get("Inventory", [])
    except (OSError, json.JSONDecodeError):
        return []


def _read_last_cargo_capacity(journal_dir: Path) -> int | None:
    journals = sorted(journal_dir.glob("Journal.*.log"), key=lambda p: p.stat().st_mtime)
    for journal_file in reversed(journals):
        try:
            with journal_file.open(encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            cargo_capacity = event.get("CargoCapacity")
            if isinstance(cargo_capacity, bool) or not isinstance(cargo_capacity, (int, float)):
                continue
            if cargo_capacity > 0:
                return int(cargo_capacity)
    return None


def _read_market_station(journal_dir: Path) -> tuple[str, str]:
    market_path = journal_dir / "Market.json"
    try:
        with market_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return "", ""
    return str(data.get("StationName", "")), str(data.get("StarSystem", ""))


def _sellable_cargo(inventory: list[dict]) -> list[dict]:
    return [
        item for item in inventory
        if item.get("Count", 0) > 0
        and item.get("Stolen", 0) == 0
        and "MissionID" not in item
    ]


def _read_latest_journal_events(journal_dir: Path) -> list[dict]:
    journals = sorted(journal_dir.glob("Journal.*.log"), key=lambda p: p.stat().st_mtime)
    if not journals:
        return []
    events: list[dict] = []
    try:
        with journals[-1].open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return events


class _TransitResumeState(Enum):
    NONE = auto()
    ARRIVED_IN_DESTINATION_SYSTEM = auto()
    POST_DROP_NEAR_STATION = auto()
    AWAITING_DOCKED = auto()


def _detect_transit_resume_state(events: list[dict], destination_leg: StationLeg) -> _TransitResumeState:
    destination_station = destination_leg.station.lower()
    destination_system = destination_leg.system.lower()

    for event in reversed(events):
        evt_name = str(event.get("event", ""))

        if evt_name in {"DockingRequested", "DockingGranted"}:
            station_name = str(event.get("StationName", "")).lower()
            return (
                _TransitResumeState.AWAITING_DOCKED
                if destination_station and station_name == destination_station
                else _TransitResumeState.NONE
            )

        if evt_name == "SupercruiseExit":
            body_type = str(event.get("BodyType", "")).lower()
            system_name = str(event.get("StarSystem", "")).lower()
            if body_type != "station":
                return _TransitResumeState.NONE
            return (
                _TransitResumeState.POST_DROP_NEAR_STATION
                if not destination_system or not system_name or system_name == destination_system
                else _TransitResumeState.NONE
            )

        if evt_name in {"SupercruiseEntry", "FSDJump"}:
            system_name = str(event.get("StarSystem", "")).lower()
            return (
                _TransitResumeState.ARRIVED_IN_DESTINATION_SYSTEM
                if not destination_system or not system_name or system_name == destination_system
                else _TransitResumeState.NONE
            )

        if evt_name == "Undocked":
            return _TransitResumeState.NONE

    return _TransitResumeState.NONE


def _inventory_has_commodity(inventory: list[dict], commodity: str) -> bool:
    commodity_lower = commodity.lower()
    return any(
        item.get("Count", 0) > 0
        and (
            str(item.get("Name", "")).lower() == commodity_lower
            or str(item.get("Name_Localised", "")).lower() == commodity_lower
        )
        for item in inventory
    )


def _inventory_commodity_count(inventory: list[dict], commodity: str) -> int:
    commodity_lower = commodity.lower()
    total = 0
    for item in inventory:
        count = item.get("Count", 0)
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            continue
        if (
            str(item.get("Name", "")).lower() == commodity_lower
            or str(item.get("Name_Localised", "")).lower() == commodity_lower
        ):
            total += max(0, int(count))
    return total


def _inventory_used_capacity(inventory: list[dict]) -> int:
    used = 0
    for item in inventory:
        count = item.get("Count", 0)
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            continue
        used += max(0, int(count))
    return used


def _inventory_has_full_commodity_load(
    inventory: list[dict],
    *,
    commodity: str,
    cargo_capacity: int | None,
) -> bool | None:
    if cargo_capacity is None or cargo_capacity <= 0:
        return None
    commodity_count = _inventory_commodity_count(inventory, commodity)
    used_capacity = _inventory_used_capacity(inventory)
    return commodity_count >= cargo_capacity and used_capacity == commodity_count


class Phase(Enum):
    AT_STATION_1_SELL = auto()
    AT_STATION_1_BUY = auto()
    UNDOCK_STATION_1 = auto()
    DEPART_STATION_1_SYSTEM = auto()
    TRANSIT_TO_STATION_2 = auto()
    AT_STATION_2_SELL = auto()
    AT_STATION_2_BUY = auto()
    UNDOCK_STATION_2 = auto()
    DEPART_STATION_2_SYSTEM = auto()
    TRANSIT_TO_STATION_1 = auto()


@dataclass(frozen=True)
class StationLeg:
    index: int
    station: str
    system: str
    buy_commodity: str
    sell_commodity: str

    @property
    def label(self) -> str:
        return f"station {self.index} ({self.station})" if self.station else f"station {self.index}"


@dataclass
class _HaulCtx:
    controls: SupportsHaulControls
    watcher: SupportsPollEvents
    journal_dir: Path
    market_path: Path
    station_1: StationLeg
    station_2: StationLeg
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


def _engage_hyperspace_after_escape(ctx: _HaulCtx) -> None:
    if not ctx.auto_hyperspace_engage:
        return
    ctx.progress_fn('Mass lock cleared - engaging hyperspace via raw key "k"...')
    ctx.announce_fn(AnnouncementId.STATION_CLEARED)
    ctx.controls.tap_key("k")


def _open_navigation_panel_after_arrival(ctx: _HaulCtx) -> None:
    if not ctx.open_nav_panel_after_hyperspace_arrival:
        return
    if ctx.nav_panel_open_delay_s > 0:
        ctx.progress_fn(f"Waiting {ctx.nav_panel_open_delay_s:.1f}s before opening navigation panel...")
        ctx.sleeper(ctx.nav_panel_open_delay_s)
    ctx.progress_fn("Hyperspace complete - opening left panel for navigation...")
    dispatch = ctx.controls.focus_left_panel()
    if dispatch.status != "ok":
        ctx.progress_fn(f"Warning: could not open left panel ({dispatch.reason or dispatch.status}); continuing")


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


def _detect_start_phase(
    journal_dir: Path,
    *,
    station_1: StationLeg,
    station_2: StationLeg,
    progress_fn: ProgressCallback,
) -> Phase:
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

    inventory = _read_cargo_json(journal_dir)
    has_station_1_cargo = _inventory_has_commodity(inventory, station_1.buy_commodity)
    has_station_2_cargo = _inventory_has_commodity(inventory, station_2.buy_commodity)
    cargo_capacity = _read_last_cargo_capacity(journal_dir)
    has_full_station_1_cargo = _inventory_has_full_commodity_load(
        inventory,
        commodity=station_1.buy_commodity,
        cargo_capacity=cargo_capacity,
    )
    has_full_station_2_cargo = _inventory_has_full_commodity_load(
        inventory,
        commodity=station_2.buy_commodity,
        cargo_capacity=cargo_capacity,
    )
    market_station, market_system = _read_market_station(journal_dir)

    if ship_status in {"docked", "unknown"}:
        if not current_station and market_station:
            current_station = market_station
        if not current_system and market_system:
            current_system = market_system
        if current_station:
            ship_status = "docked"

    progress_fn(
        "Two-way phase detect: "
        f"status={ship_status}, station={current_station!r}, system={current_system!r}, "
        f"has_station_1_cargo={has_station_1_cargo}, has_station_2_cargo={has_station_2_cargo}, "
        f"full_station_1_cargo={has_full_station_1_cargo}, full_station_2_cargo={has_full_station_2_cargo}"
    )

    if ship_status == "unknown":
        return Phase.AT_STATION_1_SELL

    current_station_lower = current_station.lower()
    station_1_lower = station_1.station.lower()
    station_2_lower = station_2.station.lower()
    current_system_lower = current_system.lower()
    station_1_system_lower = station_1.system.lower()
    station_2_system_lower = station_2.system.lower()

    if ship_status == "docked":
        if current_station_lower == station_1_lower:
            if has_station_2_cargo:
                return Phase.AT_STATION_1_SELL
            if has_full_station_1_cargo:
                return Phase.UNDOCK_STATION_1
            return Phase.AT_STATION_1_BUY
        if current_station_lower == station_2_lower:
            if has_station_1_cargo:
                return Phase.AT_STATION_2_SELL
            if has_full_station_2_cargo:
                return Phase.UNDOCK_STATION_2
            return Phase.AT_STATION_2_BUY
        raise RuntimeError(
            f"Docked at unknown station {current_station!r}, expected {station_1.station!r} or {station_2.station!r}"
        )

    if current_system_lower and station_1_system_lower and current_system_lower == station_1_system_lower:
        if has_station_2_cargo:
            return Phase.TRANSIT_TO_STATION_1
        if has_full_station_1_cargo and ship_status == "normal_space":
            return Phase.DEPART_STATION_1_SYSTEM
        if ship_status == "normal_space":
            return Phase.DEPART_STATION_1_SYSTEM
        return Phase.TRANSIT_TO_STATION_2

    if current_system_lower and station_2_system_lower and current_system_lower == station_2_system_lower:
        if has_station_1_cargo:
            return Phase.TRANSIT_TO_STATION_2
        if has_full_station_2_cargo and ship_status == "normal_space":
            return Phase.DEPART_STATION_2_SYSTEM
        if ship_status == "normal_space":
            return Phase.DEPART_STATION_2_SYSTEM
        return Phase.TRANSIT_TO_STATION_1

    if has_station_1_cargo:
        return Phase.TRANSIT_TO_STATION_2
    if has_station_2_cargo:
        return Phase.TRANSIT_TO_STATION_1
    return Phase.AT_STATION_1_SELL


def _run_market_sell(
    ctx: _HaulCtx,
    *,
    leg: StationLeg,
    next_phase: Phase,
) -> tuple[RoutineResult, Phase]:
    if not _sellable_cargo(_read_cargo_json(ctx.journal_dir)):
        ctx.progress_fn(f"Cargo hold empty - skipping {leg.label} sell.")
        return (
            RoutineResult(
                action="market_sell",
                dispatch=ActionDispatchResult(
                    action="market_sell",
                    status="ok",
                    reason="cargo hold empty",
                ),
            ),
            next_phase,
        )
    ctx.progress_fn(f"Selling {leg.sell_commodity} at {leg.label} (MAX)...")
    ctx.announce_fn(AnnouncementId.SELLING_CARGO, commodity_name=leg.sell_commodity)
    result = market_sell(
        ctx.controls,
        ctx.watcher,
        market_path=ctx.market_path,
        target=leg.sell_commodity,
        amount="MAX",
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
        return result, next_phase
    # market_sell finishes with UI_Back x2, which returns us to the station
    # services menu. The next phase (buy) immediately presses UI_Select to
    # re-enter station services, and that select can land on stale UI if the
    # menu has not finished redrawing. Settle here, on the sell side, because
    # the gap exists only when we just came out of the menu - resume paths
    # that drop straight into AT_STATION_*_BUY do not need it.
    if ctx.post_sell_settle_s > 0:
        ctx.sleeper(ctx.post_sell_settle_s)
    return result, next_phase


def _run_market_buy(
    ctx: _HaulCtx,
    *,
    leg: StationLeg,
    next_phase: Phase,
) -> tuple[RoutineResult, Phase]:
    ctx.progress_fn(f"Buying {leg.buy_commodity} at {leg.label} (MAX)...")
    ctx.announce_fn(AnnouncementId.BUYING_CARGO, commodity_name=leg.buy_commodity)
    result = market_buy(
        ctx.controls,
        ctx.watcher,
        market_path=ctx.market_path,
        target=leg.buy_commodity,
        amount="MAX",
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
        return result, next_phase
    return result, next_phase


def _should_stop_before_station_1_buy(
    phase: Phase,
    stop_requested_fn: Callable[[], bool] | None,
) -> bool:
    return phase == Phase.AT_STATION_1_BUY and stop_requested_fn is not None and stop_requested_fn()


def _stopped_routine_result(reason: str) -> RoutineResult:
    return RoutineResult(
        action="haul_loop",
        dispatch=ActionDispatchResult(
            action="haul_loop",
            status="ok",
            reason=reason,
        ),
    )


def _undock_and_route(
    ctx: _HaulCtx,
    *,
    current_leg: StationLeg,
    destination_system: str,
    next_phase: Phase,
) -> tuple[RoutineResult, Phase]:
    ctx.progress_fn(f"Undocking from {current_leg.label}...")
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
        return result, next_phase

    if destination_system:
        ctx.progress_fn(f"Setting galaxy map destination: {destination_system}...")
        ctx.announce_fn(AnnouncementId.DESTINATION_SET, system_name=destination_system)
        set_gal_map_destination(
            ctx.controls,
            destination=destination_system,
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
        ctx.progress_fn(
            "Error: "
            f"{clear_result.dispatch.reason}; haul aborted. You can resume haul with replay / ctrl-r."
        )
        ctx.announce_fn(AnnouncementId.HAUL_ABORTED)
        return clear_result, next_phase
    escape_mass_lock(
        ctx.controls,
        journal_dir=ctx.journal_dir,
        step_delay_s=ctx.step_delay_s,
        boost_delay_s=ctx.mass_lock_boost_delay_s,
        sleeper=ctx.sleeper,
        progress_fn=ctx.progress_fn,
    )
    _engage_hyperspace_after_escape(ctx)
    return (
        clear_result if clear_result.dispatch.status == "ok" else result,
        next_phase,
    )


def _depart_system(
    ctx: _HaulCtx,
    *,
    current_leg: StationLeg,
    destination_system: str,
    next_phase: Phase,
) -> tuple[RoutineResult | None, Phase]:
    ctx.progress_fn(f"Departing {current_leg.label} system in normal space...")
    if destination_system:
        ctx.progress_fn(f"Setting galaxy map destination: {destination_system}...")
        ctx.announce_fn(AnnouncementId.DESTINATION_SET, system_name=destination_system)
        set_gal_map_destination(
            ctx.controls,
            destination=destination_system,
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
    return None, next_phase


def _run_transit(
    ctx: _HaulCtx,
    *,
    destination_leg: StationLeg,
    next_phase: Phase,
) -> tuple[RoutineResult, Phase]:
    recent_events = _read_latest_journal_events(ctx.journal_dir)
    resume_state = _detect_transit_resume_state(recent_events, destination_leg)
    pending_events: list[dict[str, object]] = []
    if resume_state == _TransitResumeState.AWAITING_DOCKED:
        ctx.progress_fn(f"Docking already in progress for {destination_leg.label} - waiting for Docked.")
    elif resume_state == _TransitResumeState.ARRIVED_IN_DESTINATION_SYSTEM:
        ctx.progress_fn(f"Already in supercruise in {destination_leg.label} system - opening navigation panel.")
    elif resume_state == _TransitResumeState.POST_DROP_NEAR_STATION:
        ctx.progress_fn(f"Already in normal space near {destination_leg.label} - skipping drop wait.")
    else:
        ctx.progress_fn(f"Waiting for hyperspace arrival in {destination_leg.label} system...")

    if resume_state == _TransitResumeState.AWAITING_DOCKED:
        return (
            station_refuel_menu(
                ctx.controls,
                ctx.watcher,
                dock_timeout_s=ctx.dock_timeout_s,
                settle_s=ctx.settle_s,
                time_fn=ctx.time_fn,
                sleeper=ctx.sleeper,
                progress_fn=ctx.progress_fn,
            ),
            next_phase,
        )

    if resume_state == _TransitResumeState.NONE:
        arrival_observed, pending_events = _wait_for_arrival_or_approach_event(
            ctx.watcher,
            deadline=ctx.time_fn() + ctx.dock_timeout_s,
            time_fn=ctx.time_fn,
        )
        if not arrival_observed:
            ctx.progress_fn("Warning: hyperspace arrival event not observed; continuing toward station.")
        else:
            ctx.progress_fn("Arrived in destination system")
            _open_navigation_panel_after_arrival(ctx)
    elif resume_state == _TransitResumeState.ARRIVED_IN_DESTINATION_SYSTEM:
        _open_navigation_panel_after_arrival(ctx)

    result = dock(
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
        announce_station_name=destination_leg.station,
    )
    return result, next_phase


def _run_station_1_sell(ctx: _HaulCtx) -> tuple[RoutineResult, Phase]:
    return _run_market_sell(ctx, leg=ctx.station_1, next_phase=Phase.AT_STATION_1_BUY)


def _run_station_1_buy(ctx: _HaulCtx) -> tuple[RoutineResult, Phase]:
    return _run_market_buy(ctx, leg=ctx.station_1, next_phase=Phase.UNDOCK_STATION_1)


def _run_undock_station_1(ctx: _HaulCtx) -> tuple[RoutineResult, Phase]:
    return _undock_and_route(
        ctx,
        current_leg=ctx.station_1,
        destination_system=ctx.station_2.system,
        next_phase=Phase.TRANSIT_TO_STATION_2,
    )


def _run_depart_station_1_system(ctx: _HaulCtx) -> tuple[RoutineResult | None, Phase]:
    return _depart_system(
        ctx,
        current_leg=ctx.station_1,
        destination_system=ctx.station_2.system,
        next_phase=Phase.TRANSIT_TO_STATION_2,
    )


def _run_transit_to_station_2(ctx: _HaulCtx) -> tuple[RoutineResult, Phase]:
    return _run_transit(ctx, destination_leg=ctx.station_2, next_phase=Phase.AT_STATION_2_SELL)


def _run_station_2_sell(ctx: _HaulCtx) -> tuple[RoutineResult, Phase]:
    return _run_market_sell(ctx, leg=ctx.station_2, next_phase=Phase.AT_STATION_2_BUY)


def _run_station_2_buy(ctx: _HaulCtx) -> tuple[RoutineResult, Phase]:
    return _run_market_buy(ctx, leg=ctx.station_2, next_phase=Phase.UNDOCK_STATION_2)


def _run_undock_station_2(ctx: _HaulCtx) -> tuple[RoutineResult, Phase]:
    return _undock_and_route(
        ctx,
        current_leg=ctx.station_2,
        destination_system=ctx.station_1.system,
        next_phase=Phase.TRANSIT_TO_STATION_1,
    )


def _run_depart_station_2_system(ctx: _HaulCtx) -> tuple[RoutineResult | None, Phase]:
    return _depart_system(
        ctx,
        current_leg=ctx.station_2,
        destination_system=ctx.station_1.system,
        next_phase=Phase.TRANSIT_TO_STATION_1,
    )


def _run_transit_to_station_1(ctx: _HaulCtx) -> tuple[RoutineResult, Phase]:
    return _run_transit(ctx, destination_leg=ctx.station_1, next_phase=Phase.AT_STATION_1_SELL)


_PHASE_RUNNERS: dict[Phase, Callable[[_HaulCtx], tuple[RoutineResult | None, Phase]]] = {
    Phase.AT_STATION_1_SELL: _run_station_1_sell,
    Phase.AT_STATION_1_BUY: _run_station_1_buy,
    Phase.UNDOCK_STATION_1: _run_undock_station_1,
    Phase.DEPART_STATION_1_SYSTEM: _run_depart_station_1_system,
    Phase.TRANSIT_TO_STATION_2: _run_transit_to_station_2,
    Phase.AT_STATION_2_SELL: _run_station_2_sell,
    Phase.AT_STATION_2_BUY: _run_station_2_buy,
    Phase.UNDOCK_STATION_2: _run_undock_station_2,
    Phase.DEPART_STATION_2_SYSTEM: _run_depart_station_2_system,
    Phase.TRANSIT_TO_STATION_1: _run_transit_to_station_1,
}


def haul_loop_two_way(
    controls: SupportsHaulControls,
    watcher: SupportsPollEvents,
    *,
    journal_dir: Path,
    station_1: str,
    station_1_buying: str,
    station_1_system: str = "",
    station_2: str,
    station_2_buying: str,
    station_2_system: str = "",
    iterations: int = 0,
    start_phase: Phase | None = None,
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
    if iterations < 0:
        raise ValueError("iterations must be non-negative (0 = infinite)")
    if not station_1 or not station_2:
        raise RuntimeError("station_1 and station_2 are required")
    if not station_1_buying or not station_2_buying:
        raise RuntimeError("station_1_buying and station_2_buying are required")
    if station_1 == station_2:
        raise RuntimeError("station_1 and station_2 must differ")
    if station_1_buying == station_2_buying:
        raise RuntimeError("station_1_buying and station_2_buying must differ")

    ctx = _HaulCtx(
        controls=controls,
        watcher=watcher,
        journal_dir=journal_dir,
        market_path=journal_dir / "Market.json",
        station_1=StationLeg(
            index=1,
            station=station_1,
            system=station_1_system,
            buy_commodity=station_1_buying,
            sell_commodity=station_2_buying,
        ),
        station_2=StationLeg(
            index=2,
            station=station_2,
            system=station_2_system,
            buy_commodity=station_2_buying,
            sell_commodity=station_1_buying,
        ),
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

    resolved_start_phase = start_phase or _detect_start_phase(
        journal_dir,
        station_1=ctx.station_1,
        station_2=ctx.station_2,
        progress_fn=progress_fn,
    )
    if resolved_start_phase != Phase.AT_STATION_1_SELL:
        progress_fn(f"Resuming from phase: {resolved_start_phase.name}")

    last_result: RoutineResult | None = None
    iteration = 0
    first_cycle = True
    while iterations == 0 or iteration < iterations:
        iteration += 1
        iter_label = f" of {iterations}" if iterations > 0 else ""
        progress_fn(f"=== Two-way haul iteration {iteration}{iter_label} ===")
        phase = resolved_start_phase if first_cycle else Phase.AT_STATION_1_SELL
        first_cycle = False

        while True:
            if _should_stop_before_station_1_buy(phase, stop_requested_fn):
                progress_fn("Stop requested at station 1; halting before station 1 buy.")
                return last_result or _stopped_routine_result("stopped before station 1 buy")
            result, next_phase = _PHASE_RUNNERS[phase](ctx)
            if result is not None:
                last_result = result
                if result.dispatch.status != "ok":
                    return result
            if (
                phase == Phase.AT_STATION_1_SELL
                and stop_requested_fn is not None
                and stop_requested_fn()
            ):
                progress_fn("Stop requested at cycle boundary; halting before station 1 buy.")
                return last_result or _stopped_routine_result("stopped at station 1 cycle boundary")
            if phase == Phase.TRANSIT_TO_STATION_1:
                break
            phase = next_phase

        progress_fn(f"Iteration {iteration} complete.")

    assert last_result is not None
    return last_result
