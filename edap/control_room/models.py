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
    destination_system: str | None = None
    destination_body: str | None = None
    destination_name: str | None = None


@dataclass
class MarketData:
    station: str = ""
    system: str = ""
    timestamp: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)
    locked: bool = False


@dataclass
class HaulStats:
    station_1_buying: str = ""
    station_2_buying: str = ""
    station_1: str = ""
    station_2: str = ""
    active: bool = False
    clean_run_active: bool = False
    waiting_for_station_1_departure: bool = False
    resumed_mid_run: bool = False
    docked_back_at_station_1: bool = False
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


@dataclass
class PromptState:
    haul_params: dict[str, str] = field(default_factory=dict)
    haul_prompt_defaults: dict[str, str] = field(default_factory=dict)
    haul_prompt_step: str = ""
    haul_confirm_buy_station: str = ""
    haul_prompt_raw_command: str = ""
    haul_prompt_skip_delay: bool = False
    dest_prompt_destination: str = ""
    dest_prompt_settle_default: float | None = None
    dest_prompt_raw_command: str = ""
    dest_prompt_skip_delay: bool = False


@dataclass
class HistoryState:
    entries: list[str] = field(default_factory=list)
    pos: int = 0
    draft: str = ""


@dataclass
class ReplayBrowserState:
    entries: list[ReplaySelection] = field(default_factory=list)
    open: bool = False
    filter_text: str = ""


@dataclass
class RuntimeUIState:
    routine_active: bool = False
    active_routine_name: str | None = None
    verbose_controls: bool = False
    instant_mode: bool = False
    sigint_pending: bool = False
    shutdown_requested: bool = False
    shutdown_finalized: bool = False
