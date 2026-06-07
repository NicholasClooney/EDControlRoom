from __future__ import annotations

from typing import Any, Callable, Protocol

from edap.control_room.models import HaulStats, ShipState


class HaulTrackingHost(Protocol):
    _haul_stats: HaulStats
    _ship: ShipState
    _time_fn: Callable[[], float]

    def _refresh_haul_stats(self) -> None: ...


def start_haul_stats(
    app: HaulTrackingHost,
    *,
    commodity: str,
    buy_station: str,
    sell_station: str,
) -> None:
    at_sell_station = bool(
        sell_station
        and app._ship.status == "in_station"
        and app._ship.station
        and app._ship.station.lower() == sell_station.lower()
    )
    app._haul_stats = HaulStats(
        commodity=commodity,
        buy_station=buy_station,
        sell_station=sell_station,
        active=True,
        current_run_started_at=app._time_fn(),
        waiting_for_sell_departure=at_sell_station,
        resumed_mid_run=not at_sell_station,
    )
    app._refresh_haul_stats()


def stop_haul_stats(app: HaulTrackingHost) -> None:
    if not app._haul_stats.commodity:
        return
    app._haul_stats.active = False
    app._refresh_haul_stats()


def finalize_completed_haul_run(app: HaulTrackingHost) -> None:
    stats = app._haul_stats
    if not stats.clean_run_active:
        return
    elapsed = stats.current_run_elapsed_s
    if elapsed is None and stats.current_run_started_at is not None:
        elapsed = app._time_fn() - stats.current_run_started_at
    if elapsed is None:
        return
    stats.completed_runs += 1
    stats.last_run_elapsed_s = elapsed
    stats.last_run_profit = stats.current_run_profit
    stats.total_run_elapsed_s += elapsed
    stats.accumulated_profit += stats.current_run_profit
    stats.current_run_profit = 0
    stats.current_run_started_at = app._time_fn()
    stats.current_run_elapsed_s = None
    stats.docked_back_at_sell = False
    stats.waiting_for_sell_departure = False
    stats.resumed_mid_run = False


def handle_haul_event(
    app: HaulTrackingHost,
    ev: dict[str, Any],
    *,
    station_before: str | None,
) -> None:
    stats = app._haul_stats
    if not stats.active or not stats.commodity or not stats.sell_station:
        return

    event = ev.get("event", "")
    current_station = station_before or app._ship.station
    at_sell = bool(current_station and current_station.lower() == stats.sell_station.lower())
    at_buy = bool(
        stats.buy_station
        and current_station
        and current_station.lower() == stats.buy_station.lower()
    )

    if event == "Undocked" and at_sell:
        if stats.docked_back_at_sell:
            finalize_completed_haul_run(app)
        elif stats.current_run_started_at is None:
            stats.current_run_started_at = app._time_fn()
            stats.current_run_elapsed_s = None
        stats.clean_run_active = True
        stats.waiting_for_sell_departure = False
        stats.resumed_mid_run = False
        stats.docked_back_at_sell = False
        stats.current_run_profit = 0
    elif event == "Docked" and ev.get("StationName", "").lower() == stats.sell_station.lower():
        if stats.clean_run_active and stats.current_run_started_at is not None:
            stats.current_run_elapsed_s = app._time_fn() - stats.current_run_started_at
            stats.docked_back_at_sell = True
        elif stats.resumed_mid_run:
            if stats.current_run_started_at is not None:
                stats.current_run_elapsed_s = app._time_fn() - stats.current_run_started_at
            stats.resumed_mid_run = False
            stats.waiting_for_sell_departure = True
    elif event == "MarketBuy" and stats.clean_run_active and at_buy and "TotalCost" in ev:
        stats.current_run_profit -= int(ev["TotalCost"])
    elif event == "MarketSell" and stats.clean_run_active and at_sell and "TotalSale" in ev:
        stats.current_run_profit += int(ev["TotalSale"])

    app._refresh_haul_stats()
