from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from time import monotonic, sleep
from typing import Callable

from edap.routines._base import RoutineResult, SupportsHaulControls, SupportsPollEvents
from edap.routines.docking import _undock_until_undocked, _wait_for_clear_of_station, dock
from edap.routines.escape import escape_mass_lock
from edap.routines.galaxy_map import set_gal_map_destination
from edap.routines.market import market_buy, market_sell


class Phase(Enum):
    SELL = auto()
    UNDOCK_SELL = auto()
    DEPART_SELL_SYSTEM = auto()
    TRANSIT_TO_BUY = auto()
    BUY = auto()
    UNDOCK_BUY = auto()
    DEPART_BUY_SYSTEM = auto()
    TRANSIT_TO_SELL = auto()


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


def _read_latest_journal_events(journal_dir: Path) -> list[dict]:
    """Return all events from the most-recently-modified journal file."""
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


def _detect_phase(
    journal_dir: Path,
    *,
    sell_station: str,
    buy_station: str,
    sell_system: str,
    buy_system: str,
    commodity: str,
    confirm_fn: Callable[[str], bool],
    progress_fn: Callable[[str], None] | None = None,
) -> tuple[Phase, str]:
    """Detect which phase to resume from based on journal state and cargo.

    Returns (phase, possibly-updated buy_station).
    Raises RuntimeError when the state is unresolvable.
    """
    if not commodity:
        raise RuntimeError("commodity must not be empty")
    if sell_station and buy_station and sell_station == buy_station:
        raise RuntimeError(
            f"sell_station and buy_station must differ, both are {sell_station!r}"
        )

    events = _read_latest_journal_events(journal_dir)

    # Find the most recent position event to determine ship status.
    position_event_types = {"Docked", "Undocked", "SupercruiseEntry", "SupercruiseExit", "Location", "FSDJump"}
    latest_position: dict | None = None
    for event in reversed(events):
        if event.get("event") in position_event_types:
            latest_position = event
            break

    if latest_position is None:
        ship_status = "unknown"
        current_station = ""
        current_system = ""
    else:
        evt_name = latest_position.get("event", "")
        if evt_name == "Docked":
            ship_status = "docked"
            current_station = str(latest_position.get("StationName", ""))
            current_system = str(latest_position.get("StarSystem", ""))
        elif evt_name in {"SupercruiseEntry", "FSDJump"}:
            ship_status = "supercruise"
            current_station = ""
            current_system = str(latest_position.get("StarSystem", ""))
        elif evt_name == "SupercruiseExit":
            ship_status = "normal_space"
            current_station = ""
            current_system = str(latest_position.get("StarSystem", ""))
        elif evt_name == "Undocked":
            ship_status = "normal_space"
            current_station = ""
            current_system = str(latest_position.get("StarSystem", ""))
        elif evt_name == "Location":
            docked = latest_position.get("Docked", False)
            ship_status = "docked" if docked else "normal_space"
            current_station = str(latest_position.get("StationName", "")) if docked else ""
            current_system = str(latest_position.get("StarSystem", ""))
        else:
            ship_status = "unknown"
            current_station = ""
            current_system = ""

    # Cargo state
    inventory = _read_cargo_json(journal_dir)
    commodity_lower = commodity.lower()
    has_target_cargo = any(
        item.get("Count", 0) > 0
        and (
            str(item.get("Name", "")).lower() == commodity_lower
            or str(item.get("Name_Localised", "")).lower() == commodity_lower
        )
        for item in inventory
    )

    if progress_fn is not None:
        progress_fn(
            f"Phase detect: status={ship_status}, station={current_station!r}, "
            f"system={current_system!r}, has_target={has_target_cargo}"
        )

    if ship_status == "docked":
        station_lower = current_station.lower()
        sell_lower = sell_station.lower() if sell_station else ""
        buy_lower = buy_station.lower() if buy_station else ""

        if sell_lower and station_lower == sell_lower:
            phase = Phase.SELL if has_target_cargo else Phase.UNDOCK_SELL
            return phase, buy_station

        if buy_lower and station_lower == buy_lower:
            phase = Phase.BUY if not has_target_cargo else Phase.UNDOCK_BUY
            return phase, buy_station

        # Unknown station
        if not buy_station and sell_lower and station_lower != sell_lower:
            if confirm_fn(f"Assume current station {current_station!r} is the buy station?"):
                updated_buy = current_station
                phase = Phase.BUY if not has_target_cargo else Phase.UNDOCK_BUY
                return phase, updated_buy
            raise RuntimeError(
                f"Cannot determine buy station: docked at {current_station!r} and user declined to confirm"
            )

        raise RuntimeError(
            f"Docked at unknown station {current_station!r}, "
            f"expected sell={sell_station!r} or buy={buy_station!r}"
        )

    sell_system_lower = sell_system.lower()
    buy_system_lower = buy_system.lower()
    current_system_lower = current_system.lower()

    if current_system_lower and sell_system_lower and current_system_lower == sell_system_lower:
        if has_target_cargo:
            return Phase.TRANSIT_TO_SELL, buy_station
        if ship_status == "normal_space":
            return Phase.DEPART_SELL_SYSTEM, buy_station
        return Phase.TRANSIT_TO_BUY, buy_station

    if current_system_lower and buy_system_lower and current_system_lower == buy_system_lower:
        if has_target_cargo and ship_status == "normal_space":
            return Phase.DEPART_BUY_SYSTEM, buy_station
        return (Phase.UNDOCK_BUY if has_target_cargo else Phase.TRANSIT_TO_BUY), buy_station

    # Not docked outside the configured buy/sell systems.
    if has_target_cargo:
        return Phase.TRANSIT_TO_SELL, buy_station
    return Phase.TRANSIT_TO_BUY, buy_station


@dataclass
class _HaulCtx:
    controls: SupportsHaulControls
    watcher: SupportsPollEvents
    journal_dir: Path
    market_path: Path
    commodity: str
    sell_station: str
    buy_station: str
    sell_system: str
    buy_system: str
    step_delay_s: float
    max_hold_s: float
    dock_timeout_s: float
    request_timeout_s: float
    undock_timeout_s: float
    undock_no_track_timeout_s: float
    trade_timeout_s: float
    settle_s: float
    galaxy_map_settle_s: float
    boost_settle_s: float
    deny_retry_delay_s: float
    mass_lock_boost_delay_s: float
    max_dock_retries: int
    time_fn: Callable[[], float]
    sleeper: Callable[[float], None]
    progress_fn: Callable[[str], None] | None
    sell_label: str
    buy_label: str


def _run_sell(ctx: _HaulCtx) -> tuple[RoutineResult | None, Phase | None]:
    cargo = _read_cargo_json(ctx.journal_dir)
    inventory = cargo
    commodity_lower = ctx.commodity.lower()

    # Separate target cargo from non-target sellable
    target_items = [
        item for item in inventory
        if item.get("Count", 0) > 0
        and item.get("Stolen", 0) == 0
        and "MissionID" not in item
        and (
            str(item.get("Name", "")).lower() == commodity_lower
            or str(item.get("Name_Localised", "")).lower() == commodity_lower
        )
    ]
    other_sellable = [
        item for item in _sellable_cargo(inventory)
        if not (
            str(item.get("Name", "")).lower() == commodity_lower
            or str(item.get("Name_Localised", "")).lower() == commodity_lower
        )
    ]

    if other_sellable and ctx.progress_fn is not None:
        names = ", ".join(item.get("Name_Localised") or item.get("Name", "?") for item in other_sellable)
        ctx.progress_fn(f"Note: non-target cargo in hold, leaving alone: {names}")

    if not target_items:
        if ctx.progress_fn is not None:
            ctx.progress_fn(f"No target cargo ({ctx.commodity}){ctx.sell_label} -- skipping sell phase")
        return None, Phase.UNDOCK_SELL

    if ctx.progress_fn is not None:
        names = ", ".join(item.get("Name_Localised") or item.get("Name", "?") for item in target_items)
        ctx.progress_fn(f"Selling cargo{ctx.sell_label}: {names}")

    last_result: RoutineResult | None = None
    for item in target_items:
        name = item.get("Name_Localised") or item.get("Name", "?")
        if ctx.progress_fn is not None:
            ctx.progress_fn(f"  Selling {name} (MAX)...")
        result = market_sell(
            ctx.controls, ctx.watcher,
            market_path=ctx.market_path,
            target=str(name),
            amount="MAX",
            step_delay_s=ctx.step_delay_s,
            max_hold_s=ctx.max_hold_s,
            trade_timeout_s=ctx.trade_timeout_s,
            time_fn=ctx.time_fn,
            sleeper=ctx.sleeper,
            progress_fn=ctx.progress_fn,
        )
        last_result = result
        if result.dispatch.status != "ok":
            if ctx.progress_fn is not None:
                ctx.progress_fn(f"  Skipping {name}: {result.dispatch.reason}")

    return last_result, Phase.UNDOCK_SELL


def _run_undock_sell(ctx: _HaulCtx) -> tuple[RoutineResult | None, Phase | None]:
    if ctx.progress_fn is not None:
        ctx.progress_fn(f"Undocking from sell station{ctx.sell_label}...")
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
        if ctx.progress_fn is not None:
            ctx.progress_fn(f"Undock from sell station failed: {result.dispatch.reason}")
        return result, None  # None signals abort

    if ctx.buy_system:
        if ctx.progress_fn is not None:
            ctx.progress_fn(f"Setting galaxy map destination: {ctx.buy_system}...")
        set_gal_map_destination(
            ctx.controls,
            destination=ctx.buy_system,
            journal_dir=ctx.journal_dir,
            step_delay_s=ctx.step_delay_s,
            map_settle_s=ctx.galaxy_map_settle_s,
            time_fn=ctx.time_fn,
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
        if ctx.progress_fn is not None:
            ctx.progress_fn(
                "Error: "
                f"{clear_result.dispatch.reason}; haul aborted. You can resume haul with replay / ctrl-r."
            )
        return clear_result, None
    escape_mass_lock(
        ctx.controls,
        journal_dir=ctx.journal_dir,
        step_delay_s=ctx.step_delay_s,
        boost_delay_s=ctx.mass_lock_boost_delay_s,
        sleeper=ctx.sleeper,
        progress_fn=ctx.progress_fn,
    )

    return clear_result if clear_result.dispatch.status == "ok" else result, Phase.TRANSIT_TO_BUY


def _set_departure_route_and_escape(
    ctx: _HaulCtx,
    *,
    destination: str,
) -> None:
    if destination:
        if ctx.progress_fn is not None:
            ctx.progress_fn(f"Setting galaxy map destination: {destination}...")
        set_gal_map_destination(
            ctx.controls,
            destination=destination,
            journal_dir=ctx.journal_dir,
            step_delay_s=ctx.step_delay_s,
            map_settle_s=ctx.galaxy_map_settle_s,
            time_fn=ctx.time_fn,
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


def _run_depart_sell_system(ctx: _HaulCtx) -> tuple[RoutineResult | None, Phase | None]:
    if ctx.progress_fn is not None:
        ctx.progress_fn(f"Resuming from sell system{ctx.sell_label} in normal space...")
    _set_departure_route_and_escape(ctx, destination=ctx.buy_system)
    return None, Phase.TRANSIT_TO_BUY


def _run_transit_to_buy(ctx: _HaulCtx) -> tuple[RoutineResult | None, Phase | None]:
    if ctx.progress_fn is not None:
        ctx.progress_fn(f"Waiting for drop near buy station{ctx.buy_label}...")
    result = dock(
        ctx.controls, ctx.watcher,
        wait_for_supercruise_exit=True,
        auto_refuel=True,
        max_retries=ctx.max_dock_retries,
        request_timeout_s=ctx.request_timeout_s,
        dock_timeout_s=ctx.dock_timeout_s,
        settle_s=ctx.settle_s,
        step_delay_s=ctx.step_delay_s,
        boost_settle_s=ctx.boost_settle_s,
        deny_retry_delay_s=ctx.deny_retry_delay_s,
        time_fn=ctx.time_fn,
        sleeper=ctx.sleeper,
        progress_fn=ctx.progress_fn,
    )
    if result.dispatch.status != "ok":
        if ctx.progress_fn is not None:
            ctx.progress_fn(f"Dock at buy station{ctx.buy_label} failed: {result.dispatch.reason}")
        return result, None

    return result, Phase.BUY


def _run_buy(ctx: _HaulCtx) -> tuple[RoutineResult | None, Phase | None]:
    if ctx.progress_fn is not None:
        ctx.progress_fn(f"Buying {ctx.commodity} (MAX){ctx.buy_label}...")
    result = market_buy(
        ctx.controls, ctx.watcher,
        market_path=ctx.market_path,
        target=ctx.commodity,
        amount="MAX",
        step_delay_s=ctx.step_delay_s,
        max_hold_s=ctx.max_hold_s,
        trade_timeout_s=ctx.trade_timeout_s,
        time_fn=ctx.time_fn,
        sleeper=ctx.sleeper,
        progress_fn=ctx.progress_fn,
    )
    if result.dispatch.status != "ok":
        if ctx.progress_fn is not None:
            ctx.progress_fn(f"Buy {ctx.commodity} failed: {result.dispatch.reason}")
        return result, None

    return result, Phase.UNDOCK_BUY


def _run_undock_buy(ctx: _HaulCtx) -> tuple[RoutineResult | None, Phase | None]:
    if ctx.progress_fn is not None:
        ctx.progress_fn(f"Undocking from buy station{ctx.buy_label}...")
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
        if ctx.progress_fn is not None:
            ctx.progress_fn(f"Undock from buy station failed: {result.dispatch.reason}")
        return result, None

    if ctx.sell_system:
        if ctx.progress_fn is not None:
            ctx.progress_fn(f"Setting galaxy map destination: {ctx.sell_system}...")
        set_gal_map_destination(
            ctx.controls,
            destination=ctx.sell_system,
            journal_dir=ctx.journal_dir,
            step_delay_s=ctx.step_delay_s,
            map_settle_s=ctx.galaxy_map_settle_s,
            time_fn=ctx.time_fn,
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
        if ctx.progress_fn is not None:
            ctx.progress_fn(
                "Error: "
                f"{clear_result.dispatch.reason}; haul aborted. You can resume haul with replay / ctrl-r."
            )
        return clear_result, None
    escape_mass_lock(
        ctx.controls,
        journal_dir=ctx.journal_dir,
        step_delay_s=ctx.step_delay_s,
        boost_delay_s=ctx.mass_lock_boost_delay_s,
        sleeper=ctx.sleeper,
        progress_fn=ctx.progress_fn,
    )

    return clear_result if clear_result.dispatch.status == "ok" else result, Phase.TRANSIT_TO_SELL


def _run_depart_buy_system(ctx: _HaulCtx) -> tuple[RoutineResult | None, Phase | None]:
    if ctx.progress_fn is not None:
        ctx.progress_fn(f"Resuming from buy system{ctx.buy_label} in normal space...")
    _set_departure_route_and_escape(ctx, destination=ctx.sell_system)
    return None, Phase.TRANSIT_TO_SELL


def _run_transit_to_sell(ctx: _HaulCtx) -> tuple[RoutineResult | None, Phase | None]:
    if ctx.progress_fn is not None:
        ctx.progress_fn(f"Waiting for drop near sell station{ctx.sell_label}...")
    result = dock(
        ctx.controls, ctx.watcher,
        wait_for_supercruise_exit=True,
        auto_refuel=True,
        max_retries=ctx.max_dock_retries,
        request_timeout_s=ctx.request_timeout_s,
        dock_timeout_s=ctx.dock_timeout_s,
        settle_s=ctx.settle_s,
        step_delay_s=ctx.step_delay_s,
        boost_settle_s=ctx.boost_settle_s,
        deny_retry_delay_s=ctx.deny_retry_delay_s,
        time_fn=ctx.time_fn,
        sleeper=ctx.sleeper,
        progress_fn=ctx.progress_fn,
    )
    if result.dispatch.status != "ok":
        if ctx.progress_fn is not None:
            ctx.progress_fn(f"Dock at sell station{ctx.sell_label} failed: {result.dispatch.reason}")
        return result, None

    # None signals iteration complete; caller resets to Phase.SELL
    return result, None


_PHASE_RUNNERS: dict[Phase, Callable[[_HaulCtx], tuple[RoutineResult | None, Phase | None]]] = {
    Phase.SELL: _run_sell,
    Phase.UNDOCK_SELL: _run_undock_sell,
    Phase.DEPART_SELL_SYSTEM: _run_depart_sell_system,
    Phase.TRANSIT_TO_BUY: _run_transit_to_buy,
    Phase.BUY: _run_buy,
    Phase.UNDOCK_BUY: _run_undock_buy,
    Phase.DEPART_BUY_SYSTEM: _run_depart_buy_system,
    Phase.TRANSIT_TO_SELL: _run_transit_to_sell,
}


def haul_loop(
    controls: SupportsHaulControls,
    watcher: SupportsPollEvents,
    *,
    journal_dir: Path,
    commodity: str,
    sell_station: str = "",
    buy_station: str = "",
    sell_system: str = "",
    buy_system: str = "",
    iterations: int = 0,
    step_delay_s: float = 1.0,
    max_hold_s: float = 10.0,
    dock_timeout_s: float = 600.0,
    request_timeout_s: float = 20.0,
    undock_timeout_s: float = 30.0,
    undock_no_track_timeout_s: float = 600.0,
    trade_timeout_s: float = 30.0,
    settle_s: float = 2.0,
    galaxy_map_settle_s: float = 2.0,
    boost_settle_s: float = 3.0,
    deny_retry_delay_s: float = 5.0,
    mass_lock_boost_delay_s: float = 5.0,
    max_dock_retries: int = 3,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: Callable[[str], None] | None = None,
    confirm_fn: Callable[[str], bool],
) -> RoutineResult:
    """Community hauling loop: sell target cargo, undock, transit to buy station,
    buy commodity, undock, transit to sell station, refuel, repeat.

    Resumes from the correct phase on startup using _detect_phase (journal + cargo).
    confirm_fn is called when an unknown docked station might be the buy station;
    return True to accept, False to abort.
    """
    if iterations < 0:
        raise ValueError("iterations must be non-negative (0 = infinite)")
    if not commodity:
        raise RuntimeError("commodity must not be empty")
    if sell_station and buy_station and sell_station == buy_station:
        raise RuntimeError(
            f"sell_station and buy_station must differ, both are {sell_station!r}"
        )

    market_path = journal_dir / "Market.json"
    sell_label = f" ({sell_station})" if sell_station else ""
    buy_label = f" ({buy_station})" if buy_station else ""

    ctx = _HaulCtx(
        controls=controls,
        watcher=watcher,
        journal_dir=journal_dir,
        market_path=market_path,
        commodity=commodity,
        sell_station=sell_station,
        buy_station=buy_station,
        sell_system=sell_system,
        buy_system=buy_system,
        step_delay_s=step_delay_s,
        max_hold_s=max_hold_s,
        dock_timeout_s=dock_timeout_s,
        request_timeout_s=request_timeout_s,
        undock_timeout_s=undock_timeout_s,
        undock_no_track_timeout_s=undock_no_track_timeout_s,
        trade_timeout_s=trade_timeout_s,
        settle_s=settle_s,
        galaxy_map_settle_s=galaxy_map_settle_s,
        boost_settle_s=boost_settle_s,
        deny_retry_delay_s=deny_retry_delay_s,
        mass_lock_boost_delay_s=mass_lock_boost_delay_s,
        max_dock_retries=max_dock_retries,
        time_fn=time_fn,
        sleeper=sleeper,
        progress_fn=progress_fn,
        sell_label=sell_label,
        buy_label=buy_label,
    )

    # Detect starting phase once before the iteration counter starts.
    start_phase, resolved_buy_station = _detect_phase(
        journal_dir,
        sell_station=sell_station,
        buy_station=buy_station,
        sell_system=sell_system,
        buy_system=buy_system,
        commodity=commodity,
        confirm_fn=confirm_fn,
        progress_fn=progress_fn,
    )
    ctx.buy_station = resolved_buy_station
    ctx.buy_label = f" ({resolved_buy_station})" if resolved_buy_station else buy_label

    if progress_fn is not None and start_phase != Phase.SELL:
        progress_fn(f"Resuming from phase: {start_phase.name}")

    iteration = 0
    last_result: RoutineResult | None = None

    while iterations == 0 or iteration < iterations:
        iteration += 1
        if progress_fn is not None:
            iter_label = f" of {iterations}" if iterations > 0 else ""
            progress_fn(f"=== Haul loop iteration {iteration}{iter_label} ===")

        phase: Phase | None = start_phase if iteration == 1 else Phase.SELL

        while phase is not None:
            result, next_phase = _PHASE_RUNNERS[phase](ctx)
            if result is not None:
                last_result = result
            # An error result with next_phase=None means abort the whole loop.
            # A normal completion with next_phase=None means iteration done.
            if next_phase is None and result is not None and result.dispatch.status != "ok":
                return result
            phase = next_phase

        if progress_fn is not None:
            progress_fn(f"Iteration {iteration} complete.")

    assert last_result is not None
    return last_result
