from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Callable

from rich.markup import escape

from edap.control_room import error_text
from edap.control_room import (
    commands as _commands,
    persistence as _persistence,
    prompts as _prompts,
    replay as _replay,
    routines_haul,
    routines_movement,
    routines_nav,
    routines_station,
    routines_trade,
    workers as _workers,
)
from edap.control_room_state import CommandHistoryEntry
from edap.progress_controls import ProgressShipControls

if TYPE_CHECKING:
    from edap.control_room.app import ControlRoomApp


class ControlRoomFacade:
    def __init__(
        self,
        app: ControlRoomApp,
        *,
        default_placeholder: str,
        reloadable_modules: list[Any],
    ) -> None:
        self._app = app
        self._default_placeholder = default_placeholder
        self._reloadable_modules = reloadable_modules

    def dispatch_command(self, raw: str, *, skip_delay: bool | None = None) -> None:
        _commands.dispatch(self._app, raw, skip_delay_override=skip_delay)

    def record_history_entry(self, entry: CommandHistoryEntry) -> None:
        _persistence.record_history_entry(self._app, entry)

    def show_resume_picker(self) -> None:
        _replay.show_resume_picker(self._app)

    def refresh_resume_picker(self) -> None:
        _replay.refresh_resume_picker(self._app)

    def close_resume_picker(self) -> None:
        _replay.close_resume_picker(self._app)

    def resume_execute_selected(self) -> None:
        _replay.resume_execute_selected(self._app)

    def resume_execute_selected_immediate(self) -> None:
        _replay.resume_execute_selected_immediate(self._app)

    def resume_edit_selected(self) -> None:
        _replay.resume_edit_selected(self._app)

    def resume_toggle_default_selected(self) -> None:
        _replay.resume_toggle_default_selected(self._app)

    def load_market_json(self) -> None:
        from edap.control_room import bootstrap as _bootstrap

        _bootstrap.load_market_json(self._app)

    def check_routine_ready(self) -> bool:
        return _workers.check_routine_ready(self._app)

    def make_progress(self) -> Callable[[str], None]:
        return _workers.make_progress(self._app)

    def make_controls(self, progress_fn: Callable[[str], None]) -> ProgressShipControls:
        return _workers.make_controls(self._app, progress_fn)

    def make_watcher(self) -> Any:
        return _workers.make_watcher(self._app)

    def make_sleeper(self) -> Callable[[float], None]:
        return _workers.make_sleeper()

    def start_delayed_routine(
        self,
        *,
        description: str,
        start_message: str,
        fn: Callable[[], Any],
        skip_delay: bool = False,
        active_routine_name: str | None = None,
        on_start: Callable[[], None] | None = None,
    ) -> None:
        _workers.start_delayed_routine(
            self._app,
            description=description,
            start_message=start_message,
            fn=fn,
            skip_delay=skip_delay,
            active_routine_name=active_routine_name,
            on_start=on_start,
        )

    def raise_if_worker_cancelled(self) -> None:
        _workers.raise_if_worker_cancelled()

    def cmd_dock(self, *, skip_delay: bool = False) -> None:
        routines_station.cmd_dock(self._app, skip_delay=skip_delay)

    def cmd_undock(self, *, skip_delay: bool = False) -> None:
        routines_station.cmd_undock(self._app, skip_delay=skip_delay)

    def cmd_jump(self, *, skip_delay: bool = False) -> None:
        routines_movement.cmd_jump(self._app, skip_delay=skip_delay)

    def cmd_escape(self, *, skip_delay: bool = False) -> None:
        routines_movement.cmd_escape(self._app, skip_delay=skip_delay)

    def cmd_boost(self, *, skip_delay: bool = False) -> None:
        routines_movement.cmd_boost(self._app, skip_delay=skip_delay)

    def start_dest_prompt(
        self,
        destination: str,
        *,
        settle_default: float | None = None,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None:
        _prompts.start_dest_prompt(
            self._app,
            destination,
            settle_default=settle_default,
            skip_delay=skip_delay,
            raw_command=raw_command,
        )

    def cmd_dest(
        self,
        destination: str,
        *,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None:
        routines_nav.cmd_dest(
            self._app,
            destination,
            skip_delay=skip_delay,
            raw_command=raw_command,
        )

    def dispatch_dest(
        self,
        destination: str,
        galaxy_map_settle: float,
        *,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None:
        routines_nav.dispatch_dest(
            self._app,
            destination,
            galaxy_map_settle,
            skip_delay=skip_delay,
            raw_command=raw_command,
        )

    def saved_haul_defaults(self, seed: dict[str, str] | None = None) -> dict[str, str]:
        return _prompts.saved_haul_defaults(self._app, seed)

    def start_haul_prompt(
        self,
        *,
        commodity: str,
        prompt_for_commodity: bool,
        seed: dict[str, str] | None = None,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None:
        _prompts.start_haul_prompt(
            self._app,
            commodity=commodity,
            prompt_for_commodity=prompt_for_commodity,
            seed=seed,
            skip_delay=skip_delay,
            raw_command=raw_command,
        )

    def cmd_buy(self, rest: str, *, skip_delay: bool = False) -> None:
        routines_trade.cmd_buy(self._app, rest, skip_delay=skip_delay)

    def cmd_sell(self, rest: str, *, skip_delay: bool = False) -> None:
        routines_trade.cmd_sell(self._app, rest, skip_delay=skip_delay)

    def sell_item(self, target: str, amount: int | str, *, skip_delay: bool = False) -> None:
        routines_trade.sell_item(self._app, target, amount, skip_delay=skip_delay)

    def sell_all(self, *, skip_delay: bool = False) -> None:
        routines_trade.sell_all(self._app, skip_delay=skip_delay)

    def cmd_haul(
        self,
        rest: str,
        *,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None:
        routines_haul.cmd_haul(
            self._app,
            rest,
            skip_delay=skip_delay,
            raw_command=raw_command,
        )

    def cmd_multi_leg_haul(
        self,
        rest: str,
        *,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None:
        routines_haul.cmd_multi_leg_haul(
            self._app,
            rest,
            skip_delay=skip_delay,
            raw_command=raw_command,
        )

    def start_haul_confirm_prompt(self, station: str) -> None:
        _prompts.start_haul_confirm_prompt(self._app, station)

    def handle_haul_confirm_prompt(self, value: str) -> None:
        _prompts.handle_haul_confirm_prompt(
            self._app,
            value,
            default_placeholder=self._default_placeholder,
        )

    def handle_haul_prompt(self, value: str) -> None:
        _prompts.handle_haul_prompt(
            self._app,
            value,
            default_placeholder=self._default_placeholder,
        )

    def dispatch_haul_loop(
        self,
        *,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None:
        routines_haul.dispatch_haul_loop(
            self._app,
            skip_delay=skip_delay,
            raw_command=raw_command,
        )

    def cmd_reload(self) -> None:
        reloaded: list[str] = []
        for module in self._reloadable_modules:
            try:
                importlib.reload(module)
                reloaded.append(module.__name__)
            except Exception as exc:
                self._app._log(
                    f"[red]{escape(error_text.render(self._app._config, 'reload_failed', module_name=module.__name__, error=str(exc)))}[/]"
                )
                return
        self._app._log("[green]Hot-reloaded modules:[/]")
        for name in reloaded:
            self._app._log(f"  [dim]•[/] {escape(name)}")
        self._app._log(
            "[dim]Next command dispatch will use the new code. App/widget edits still need a restart.[/]"
        )


FACADE_METHOD_MAP = {
    "_record_history_entry": "record_history_entry",
    "_show_resume_picker": "show_resume_picker",
    "_refresh_resume_picker": "refresh_resume_picker",
    "_close_resume_picker": "close_resume_picker",
    "_resume_execute_selected": "resume_execute_selected",
    "_resume_execute_selected_immediate": "resume_execute_selected_immediate",
    "_resume_edit_selected": "resume_edit_selected",
    "_resume_toggle_default_selected": "resume_toggle_default_selected",
    "_load_market_json": "load_market_json",
    "_check_routine_ready": "check_routine_ready",
    "_make_progress": "make_progress",
    "_make_controls": "make_controls",
    "_make_watcher": "make_watcher",
    "_make_sleeper": "make_sleeper",
    "_start_delayed_routine": "start_delayed_routine",
    "_raise_if_worker_cancelled": "raise_if_worker_cancelled",
    "_cmd_dock": "cmd_dock",
    "_cmd_undock": "cmd_undock",
    "_cmd_jump": "cmd_jump",
    "_cmd_escape": "cmd_escape",
    "_cmd_boost": "cmd_boost",
    "_start_dest_prompt": "start_dest_prompt",
    "_cmd_dest": "cmd_dest",
    "_dispatch_dest": "dispatch_dest",
    "_saved_haul_defaults": "saved_haul_defaults",
    "_start_haul_prompt": "start_haul_prompt",
    "_cmd_buy": "cmd_buy",
    "_cmd_sell": "cmd_sell",
    "_sell_item": "sell_item",
    "_sell_all": "sell_all",
    "_cmd_haul": "cmd_haul",
    "_cmd_multi_leg_haul": "cmd_multi_leg_haul",
    "_start_haul_confirm_prompt": "start_haul_confirm_prompt",
    "_handle_haul_confirm_prompt": "handle_haul_confirm_prompt",
    "_handle_haul_prompt": "handle_haul_prompt",
    "_dispatch_haul_loop": "dispatch_haul_loop",
    "_cmd_reload": "cmd_reload",
    "_dispatch_command": "dispatch_command",
}
