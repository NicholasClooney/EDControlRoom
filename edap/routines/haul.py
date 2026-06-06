from __future__ import annotations

import json
from pathlib import Path
from time import monotonic, sleep
from typing import Callable

from edap.routines._base import RoutineResult, SupportsHaulControls, SupportsPollEvents
from edap.routines.docking import dock, undock
from edap.routines.galaxy_map import set_gal_map_destination
from edap.routines.market import market_buy, market_sell


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
    sell_system: str = "",
    buy_system: str = "",
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

        if buy_system:
            if progress_fn is not None:
                progress_fn(f"Setting galaxy map destination: {buy_system}...")
            set_gal_map_destination(
                controls,
                destination=buy_system,
                journal_dir=journal_dir,
                step_delay_s=step_delay_s,
                progress_fn=progress_fn,
            )

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

        if sell_system:
            if progress_fn is not None:
                progress_fn(f"Setting galaxy map destination: {sell_system}...")
            set_gal_map_destination(
                controls,
                destination=sell_system,
                journal_dir=journal_dir,
                step_delay_s=step_delay_s,
                progress_fn=progress_fn,
            )

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
