from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from edap.control_room import rendering as _rendering
from edap.control_room.models import MarketData, ShipState
from edap.status import read_status
from edap.state import get_latest_journal_log, read_ship_state


class BootstrapHost(Protocol):
    _journal_dir: Path
    _market_path: Path
    _market_mtime: float | None
    _market: MarketData
    _ship: ShipState

    def _refresh_market(self) -> None: ...


def bootstrap_ship_state(app: BootstrapHost) -> None:
    log = get_latest_journal_log(app._journal_dir)
    if log is not None:
        try:
            state = read_ship_state(log)
            app._ship.system = state.location
            app._ship.status = state.status
            app._ship.ship_type = state.ship_type
            app._ship.fuel_level = state.fuel_level
            app._ship.fuel_capacity = state.fuel_capacity
            app._ship.target = state.target
        except Exception:
            pass

    try:
        status = read_status(app._journal_dir)
    except Exception:
        status = None

    if status is not None:
        if status.balance is not None:
            app._ship.credits = status.balance
        if status.cargo is not None:
            app._ship.cargo_count = int(status.cargo)
    app._ship.cargo_inventory = _rendering.read_cargo_inventory(app._journal_dir)


def load_market_json(app: BootstrapHost) -> None:
    if app._market.locked or not app._market_path.exists():
        return
    mtime = app._market_path.stat().st_mtime
    if mtime == app._market_mtime:
        return
    app._market_mtime = mtime
    try:
        with app._market_path.open(encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
    except Exception:
        return

    app._market = MarketData(
        station=data.get("StationName", "?"),
        system=data.get("StarSystem", "?"),
        timestamp=data.get("timestamp", ""),
        items=data.get("Items", []),
        locked=app._market.locked,
    )
    app._refresh_market()
