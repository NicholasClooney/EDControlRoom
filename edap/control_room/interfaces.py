from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol

from textual.widgets import Input

from edap.config import AppConfig
from edap.control_room.models import MarketData, ShipState
from edap.control_room_state import CommandHistoryEntry, ControlRoomState
from edap.progress_controls import ProgressShipControls
from edap.tts import AnnouncementId


class CommandHost(Protocol):
    _config: AppConfig
    _verbose_controls: bool
    _instant_mode: bool
    _market_filter: str | None
    _market: MarketData
    _saved_state: ControlRoomState

    def _log(self, msg: str) -> None: ...
    def _record_history_entry(self, entry: CommandHistoryEntry) -> None: ...
    def _save_saved_state(self) -> None: ...
    def _request_shutdown(self, source: str) -> None: ...
    def _cmd_dock(self, *, skip_delay: bool = False) -> None: ...
    def _cmd_undock(self, *, skip_delay: bool = False) -> None: ...
    def _cmd_jump(self, *, skip_delay: bool = False) -> None: ...
    def _cmd_escape(self, *, skip_delay: bool = False) -> None: ...
    def _cmd_boost(self, *, skip_delay: bool = False) -> None: ...
    def _cmd_buy(self, rest: str, *, skip_delay: bool = False) -> None: ...
    def _cmd_sell(self, rest: str, *, skip_delay: bool = False) -> None: ...
    def _cmd_haul(
        self,
        rest: str,
        *,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None: ...
    def _cmd_multi_leg_haul(
        self,
        rest: str,
        *,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None: ...
    def _cmd_dest(
        self,
        destination: str,
        *,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None: ...
    def _cmd_reload(self) -> None: ...
    def _show_resume_picker(self) -> None: ...
    def _load_market_json(self) -> None: ...
    def _refresh_market(self) -> None: ...


class RoutineHost(Protocol):
    _config: AppConfig
    _controls: Any
    _routine_active: bool
    _routine_worker: Any | None
    _verbose_controls: bool
    _instant_mode: bool
    _journal_dir: Path
    _market_path: Path
    _ship: ShipState
    _active_routine_name: str | None
    _haul_stop_requested: bool

    def _log(self, msg: str) -> None: ...
    def _announce_tts(self, message_id: AnnouncementId, /, **values: object) -> None: ...
    def _check_routine_ready(self) -> bool: ...
    def _make_progress(self) -> Callable[[str], None]: ...
    def _make_controls(self, progress_fn: Callable[[str], None]) -> ProgressShipControls: ...
    def _make_watcher(self) -> Any: ...
    def _make_sleeper(self) -> Callable[[float], None]: ...
    def _start_delayed_routine(
        self,
        *,
        description: str,
        start_message: str,
        fn: Callable[[], Any],
        skip_delay: bool = False,
        active_routine_name: str | None = None,
        on_start: Callable[[], None] | None = None,
    ) -> None: ...
    def _run_in_thread(self, fn: Callable[[], Any]) -> Any: ...
    def _raise_if_worker_cancelled(self) -> None: ...
    def _clear_pending_haul_stop(self) -> None: ...
    def call_from_thread(self, callback: Callable[..., Any], *args: Any) -> None: ...


class NavigationHost(RoutineHost, Protocol):
    def _record_history_entry(self, entry: CommandHistoryEntry) -> None: ...
    def _start_dest_prompt(
        self,
        destination: str,
        *,
        settle_default: float | None = None,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None: ...


class TradeHost(RoutineHost, Protocol):
    def _record_history_entry(self, entry: CommandHistoryEntry) -> None: ...


class HaulHost(RoutineHost, Protocol):
    _haul_params: dict[str, str]

    def _record_history_entry(self, entry: CommandHistoryEntry) -> None: ...
    def _start_haul_prompt(
        self,
        *,
        commodity: str,
        prompt_for_commodity: bool,
        seed: dict[str, str] | None = None,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None: ...
    def _start_haul_confirm_prompt(self, station: str) -> None: ...
    def _start_haul_stats(
        self,
        *,
        station_1_buying: str,
        station_2_buying: str,
        station_1: str,
        station_2: str,
    ) -> None: ...
    def _stop_haul_stats(self) -> None: ...


class ReplayInputHost(Protocol):
    def set_focus(self, widget: object) -> None: ...
    def query_one(self, selector: str, widget_type: type[Input]) -> Input: ...
