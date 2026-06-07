from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from edap.control_room_state import CommandHistoryEntry


@dataclass
class ShipState:
    commander: str | None = None
    ship_type: str | None = None
    system: str | None = None
    station: str | None = None
    status: str | None = None
    fuel_level: float | None = None
    fuel_capacity: float | None = None
    credits: int | None = None
    cargo_count: int = 0
    cargo_capacity: int | None = None
    cargo_inventory: list[dict[str, Any]] = field(default_factory=list)
    target: str | None = None


@dataclass
class MarketData:
    station: str = ""
    system: str = ""
    timestamp: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)
    locked: bool = False


@dataclass
class HaulStats:
    commodity: str = ""
    buy_station: str = ""
    sell_station: str = ""
    active: bool = False
    clean_run_active: bool = False
    waiting_for_sell_departure: bool = False
    resumed_mid_run: bool = False
    docked_back_at_sell: bool = False
    current_run_started_at: float | None = None
    current_run_elapsed_s: float | None = None
    current_run_profit: int = 0
    completed_runs: int = 0
    accumulated_profit: int = 0
    last_run_profit: int | None = None
    last_run_elapsed_s: float | None = None
    total_run_elapsed_s: float = 0.0


@dataclass(frozen=True)
class CommandHelp:
    name: str
    usage: str
    summary: str
    detail: str
    aliases: tuple[str, ...] = ()


@dataclass
class ReplaySelection:
    entry: CommandHistoryEntry
    label: str
    detail: str
