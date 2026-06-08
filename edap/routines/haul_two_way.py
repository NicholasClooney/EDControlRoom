from __future__ import annotations

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


def _run_market_sell(
    ctx: _HaulCtx,
    *,
    leg: StationLeg,
    next_phase: Phase,
) -> tuple[RoutineResult, Phase]:
    if ctx.progress_fn is not None:
        ctx.progress_fn(f"Selling {leg.sell_commodity} at {leg.label} (MAX)...")
    result = market_sell(
        ctx.controls,
        ctx.watcher,
        market_path=ctx.market_path,
        target=leg.sell_commodity,
        amount="MAX",
        step_delay_s=ctx.step_delay_s,
        max_hold_s=ctx.max_hold_s,
        trade_timeout_s=ctx.trade_timeout_s,
        time_fn=ctx.time_fn,
        sleeper=ctx.sleeper,
        progress_fn=ctx.progress_fn,
    )
    if result.dispatch.status != "ok":
        return result, next_phase
    return result, next_phase


def _run_market_buy(
    ctx: _HaulCtx,
    *,
    leg: StationLeg,
    next_phase: Phase,
) -> tuple[RoutineResult, Phase]:
    if ctx.progress_fn is not None:
        ctx.progress_fn(f"Buying {leg.buy_commodity} at {leg.label} (MAX)...")
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
    )
    if result.dispatch.status != "ok":
        return result, next_phase
    return result, next_phase


def _undock_and_route(
    ctx: _HaulCtx,
    *,
    current_leg: StationLeg,
    destination_system: str,
    next_phase: Phase,
) -> tuple[RoutineResult, Phase]:
    if ctx.progress_fn is not None:
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
        if ctx.progress_fn is not None:
            ctx.progress_fn(f"Setting galaxy map destination: {destination_system}...")
        set_gal_map_destination(
            ctx.controls,
            destination=destination_system,
            journal_dir=ctx.journal_dir,
            step_delay_s=ctx.step_delay_s,
            map_settle_s=ctx.galaxy_map_settle_s,
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
    if clear_result.dispatch.status != "ok" and ctx.progress_fn is not None:
        ctx.progress_fn(f"Warning: {clear_result.dispatch.reason}; continuing with mass-lock escape")
    escape_mass_lock(
        ctx.controls,
        journal_dir=ctx.journal_dir,
        step_delay_s=ctx.step_delay_s,
        boost_delay_s=ctx.mass_lock_boost_delay_s,
        sleeper=ctx.sleeper,
        progress_fn=ctx.progress_fn,
    )
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
    if ctx.progress_fn is not None:
        ctx.progress_fn(f"Departing {current_leg.label} system in normal space...")
    if destination_system:
        if ctx.progress_fn is not None:
            ctx.progress_fn(f"Setting galaxy map destination: {destination_system}...")
        set_gal_map_destination(
            ctx.controls,
            destination=destination_system,
            journal_dir=ctx.journal_dir,
            step_delay_s=ctx.step_delay_s,
            map_settle_s=ctx.galaxy_map_settle_s,
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
    return None, next_phase


def _run_transit(
    ctx: _HaulCtx,
    *,
    destination_leg: StationLeg,
    next_phase: Phase,
) -> tuple[RoutineResult, Phase]:
    if ctx.progress_fn is not None:
        ctx.progress_fn(f"Waiting for drop near {destination_leg.label}...")
    result = dock(
        ctx.controls,
        ctx.watcher,
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
    start_phase: Phase = Phase.AT_STATION_1_SELL,
    step_delay_s: float = 1.0,
    max_hold_s: float = 10.0,
    dock_timeout_s: float = 600.0,
    request_timeout_s: float = 20.0,
    undock_timeout_s: float = 30.0,
    undock_no_track_timeout_s: float = 60.0,
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
    )

    last_result: RoutineResult | None = None
    iteration = 0
    first_cycle = True
    while iterations == 0 or iteration < iterations:
        iteration += 1
        if progress_fn is not None:
            iter_label = f" of {iterations}" if iterations > 0 else ""
            progress_fn(f"=== Two-way haul iteration {iteration}{iter_label} ===")
        phase = start_phase if first_cycle else Phase.AT_STATION_1_SELL
        first_cycle = False

        while True:
            result, next_phase = _PHASE_RUNNERS[phase](ctx)
            if result is not None:
                last_result = result
                if result.dispatch.status != "ok":
                    return result
            if phase == Phase.TRANSIT_TO_STATION_1:
                break
            phase = next_phase

        if progress_fn is not None:
            progress_fn(f"Iteration {iteration} complete.")

    assert last_result is not None
    return last_result
