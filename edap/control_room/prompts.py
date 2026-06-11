from __future__ import annotations

from typing import Protocol

from rich.markup import escape
from textual.widgets import Input

from edap.config import AppConfig
from edap.control_room import error_text
from edap.control_room.models import ShipState
from edap.control_room_state import ControlRoomState


class PromptHost(Protocol):
    _config: AppConfig
    _saved_state: ControlRoomState
    _ship: ShipState
    _haul_params: dict[str, str]
    _haul_prompt_defaults: dict[str, str]
    _haul_prompt_step: str
    _haul_confirm_buy_station: str
    _haul_prompt_raw_command: str
    _haul_prompt_skip_delay: bool
    _dest_prompt_destination: str
    _dest_prompt_settle_default: float | None
    _dest_prompt_raw_command: str
    _dest_prompt_skip_delay: bool

    def _log(self, msg: str) -> None: ...
    def _dispatch_haul_loop(
        self,
        *,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None: ...
    def _dispatch_dest(
        self,
        destination: str,
        galaxy_map_settle: float,
        *,
        skip_delay: bool = False,
        raw_command: str | None = None,
    ) -> None: ...
    def query_one(self, selector: str, widget_type: type[Input]) -> Input: ...


def start_dest_prompt(
    app: PromptHost,
    destination: str,
    *,
    settle_default: float | None = None,
    skip_delay: bool = False,
    raw_command: str | None = None,
) -> None:
    app._dest_prompt_destination = destination
    app._dest_prompt_settle_default = (
        settle_default
        if settle_default is not None
        else app._config.controls.galaxy_map_settle_seconds
    )
    app._dest_prompt_raw_command = raw_command or f"{'!' if skip_delay else ''}dest {destination}"
    app._dest_prompt_skip_delay = skip_delay
    default_settle = app._dest_prompt_settle_default
    app._log(f"Destination: [bold]{escape(destination)}[/]")
    app._log(f"[dim]Galaxy-map settle seconds? (Enter = {default_settle:.1f})[/]")
    app.query_one("#cmd", Input).placeholder = (
        f"galaxy map settle seconds (Enter = {default_settle:.1f})..."
    )


def saved_haul_defaults(
    app: PromptHost,
    seed: dict[str, str] | None = None,
) -> dict[str, str]:
    defaults = dict(app._saved_state.default_haul)
    if seed:
        defaults.update({key: value for key, value in seed.items() if value != ""})
    if not defaults.get("station_1") and app._ship.station:
        defaults["station_1"] = app._ship.station
    if not defaults.get("station_1_system") and app._ship.system:
        defaults["station_1_system"] = app._ship.system
    if not defaults.get("galaxy_map_settle"):
        defaults["galaxy_map_settle"] = str(app._config.controls.galaxy_map_settle_seconds)
    if not defaults.get("dock_timeout"):
        defaults["dock_timeout"] = str(app._config.controls.haul_dock_timeout_seconds)
    return defaults


def start_haul_prompt(
    app: PromptHost,
    *,
    commodity: str,
    prompt_for_commodity: bool,
    seed: dict[str, str] | None = None,
    skip_delay: bool = False,
    raw_command: str | None = None,
) -> None:
    app._haul_params = {
        "station_1_buying": commodity.strip(),
        "station_1": "",
        "station_1_system": "",
        "station_2_buying": "",
        "station_2": "",
        "station_2_system": "",
        "galaxy_map_settle": "",
        "dock_timeout": "",
    }
    app._haul_prompt_raw_command = raw_command or f"{'!' if skip_delay else ''}haul {commodity}".strip()
    app._haul_prompt_skip_delay = skip_delay
    app._haul_prompt_defaults = saved_haul_defaults(app, seed)
    app._log("Haul loop setup — enter parameters below:")
    if prompt_for_commodity:
        app._haul_prompt_step = "station_1_buying"
        default_commodity = app._haul_prompt_defaults.get("station_1_buying", "")
        if default_commodity:
            app._log(f"[dim]Station 1 buying? (Enter = {escape(default_commodity)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"station 1 buying (Enter = {default_commodity})..."
            )
        else:
            app._log("[dim]Station 1 buying? (this cargo will be sold at station 2)[/]")
            app.query_one("#cmd", Input).placeholder = "station 1 buying..."
        return

    app._log(
        f"Haul loop: station 1 buying = [cyan]{escape(app._haul_params['station_1_buying'])}[/]"
    )
    app._haul_prompt_step = "station_1"
    default_station_1 = app._haul_prompt_defaults.get("station_1", "")
    if default_station_1:
        app._log(f"[dim]Station 1 name? (Enter = {escape(default_station_1)})[/]")
        app.query_one("#cmd", Input).placeholder = (
            f"station 1 (Enter = {default_station_1})..."
        )
    else:
        current = app._ship.station or "current station"
        app._log(f"[dim]Station 1 name? (Enter to use {escape(current)})[/]")
        app.query_one("#cmd", Input).placeholder = f"station 1 (Enter = {current})..."


def start_haul_confirm_prompt(
    app: PromptHost,
    station: str,
) -> None:
    app._haul_confirm_buy_station = station
    app._log(
        f"[dim]Assume current station [cyan]{escape(station)}[/] is station 1? "
        f"(Enter = yes, no to cancel)[/]"
    )
    app.query_one("#cmd", Input).placeholder = (
        "confirm station 1? Enter = yes, no to cancel..."
    )


def handle_haul_confirm_prompt(
    app: PromptHost,
    value: str,
    *,
    default_placeholder: str,
) -> None:
    answer = value.strip().lower()
    if answer in {"", "y", "yes"}:
        station = app._haul_confirm_buy_station
        app._haul_confirm_buy_station = ""
        app._haul_params["station_1"] = station
        app._log(f"  Station 1 confirmed: [cyan]{escape(station)}[/]")
        app.query_one("#cmd", Input).placeholder = default_placeholder
        app._dispatch_haul_loop(
            skip_delay=app._haul_prompt_skip_delay,
            raw_command=app._haul_prompt_raw_command,
        )
        return
    if answer in {"n", "no"}:
        station = app._haul_confirm_buy_station
        app._haul_confirm_buy_station = ""
        app._log(
            f"[yellow]Haul launch cancelled — station 1 left unresolved "
            f"for [cyan]{escape(station)}[/].[/]"
        )
        app.query_one("#cmd", Input).placeholder = default_placeholder
        return
    app._log(f"[red]{escape(error_text.render(app._config, 'confirm_yes_no'))}[/]")


def handle_haul_prompt(
    app: PromptHost,
    value: str,
    *,
    default_placeholder: str,
) -> None:
    if app._haul_prompt_step == "station_1_buying":
        resolved = value.strip() or app._haul_prompt_defaults.get("station_1_buying", "")
        if not resolved:
            app._log(f"[red]{escape(error_text.render(app._config, 'station_1_buying_required'))}[/]")
            return
        app._haul_params["station_1_buying"] = resolved
        app._log(f"  Station 1 buying: [cyan]{escape(resolved)}[/]")
        app._haul_prompt_step = "station_1"
        default_station_1 = app._haul_prompt_defaults.get("station_1", "")
        if default_station_1:
            app._log(f"[dim]Station 1 name? (Enter = {escape(default_station_1)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"station 1 (Enter = {default_station_1})..."
            )
        else:
            current = app._ship.station or "current station"
            app._log(f"[dim]Station 1 name? (Enter to use {escape(current)})[/]")
            app.query_one("#cmd", Input).placeholder = f"station 1 (Enter = {current})..."
        return

    if app._haul_prompt_step == "station_1":
        resolved = value.strip() or app._haul_prompt_defaults.get("station_1", "")
        app._haul_params["station_1"] = resolved
        if resolved:
            app._log(f"  Station 1: [cyan]{escape(resolved)}[/]")
        else:
            app._log("  Station 1: [dim](current station)[/]")
        app._haul_prompt_step = "station_1_system"
        default_station_1_system = app._haul_prompt_defaults.get("station_1_system", "")
        if default_station_1_system:
            app._log(f"[dim]Station 1 system? (Enter = {escape(default_station_1_system)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"station 1 system (Enter = {default_station_1_system})..."
            )
        else:
            current = app._ship.system or "current system"
            app._log(f"[dim]Station 1 system? (Enter to use {escape(current)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"station 1 system (Enter = {current})..."
            )
        return

    if app._haul_prompt_step == "station_1_system":
        resolved = value.strip() or app._haul_prompt_defaults.get("station_1_system", "")
        app._haul_params["station_1_system"] = resolved
        if resolved:
            app._log(f"  Station 1 system: [cyan]{escape(resolved)}[/]")
        else:
            app._log("  Station 1 system: [dim](current system)[/]")
        app._haul_prompt_step = "station_2_buying"
        default_station_2_buying = app._haul_prompt_defaults.get("station_2_buying", "")
        if default_station_2_buying:
            app._log(f"[dim]Station 2 buying? (Enter = {escape(default_station_2_buying)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"station 2 buying (Enter = {default_station_2_buying})..."
            )
        else:
            app._log("[dim]Station 2 buying? (this cargo will be sold at station 1)[/]")
            app.query_one("#cmd", Input).placeholder = "station 2 buying..."
        return

    if app._haul_prompt_step == "station_2_buying":
        resolved = value.strip() or app._haul_prompt_defaults.get("station_2_buying", "")
        if not resolved:
            app._log(f"[red]{escape(error_text.render(app._config, 'station_2_buying_required'))}[/]")
            return
        app._haul_params["station_2_buying"] = resolved
        if resolved:
            app._log(f"  Station 2 buying: [cyan]{escape(resolved)}[/]")
        app._haul_prompt_step = "station_2"
        default_station_2 = app._haul_prompt_defaults.get("station_2", "")
        if default_station_2:
            app._log(f"[dim]Station 2 name? (Enter = {escape(default_station_2)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"station 2 (Enter = {default_station_2})..."
            )
        else:
            app._log("[dim]Station 2 name?[/]")
            app.query_one("#cmd", Input).placeholder = "station 2..."
        return

    if app._haul_prompt_step == "station_2":
        resolved = value.strip() or app._haul_prompt_defaults.get("station_2", "")
        if not resolved:
            app._log(f"[red]{escape(error_text.render(app._config, 'station_2_name_required'))}[/]")
            return
        app._haul_params["station_2"] = resolved
        if resolved:
            app._log(f"  Station 2: [cyan]{escape(resolved)}[/]")
        app._haul_prompt_step = "station_2_system"
        default_station_2_system = app._haul_prompt_defaults.get("station_2_system", "")
        if default_station_2_system:
            app._log(f"[dim]Station 2 system? (Enter = {escape(default_station_2_system)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"station 2 system (Enter = {default_station_2_system})..."
            )
        else:
            app._log("[dim]Station 2 system?[/]")
            app.query_one("#cmd", Input).placeholder = "station 2 system..."
        return

    if app._haul_prompt_step == "station_2_system":
        resolved = value.strip() or app._haul_prompt_defaults.get("station_2_system", "")
        if not resolved:
            app._log(f"[red]{escape(error_text.render(app._config, 'station_2_system_required'))}[/]")
            return
        app._haul_params["station_2_system"] = resolved
        app._log(f"  Station 2 system: [cyan]{escape(resolved)}[/]")
        default_settle = float(
            app._haul_prompt_defaults.get(
                "galaxy_map_settle",
                app._config.controls.galaxy_map_settle_seconds,
            )
        )
        app._haul_prompt_step = "galaxy_map_settle"
        app._log(f"[dim]Galaxy-map settle seconds? (Enter = {default_settle:.1f})[/]")
        app.query_one("#cmd", Input).placeholder = (
            f"galaxy map settle seconds (Enter = {default_settle:.1f})..."
        )
        return

    if app._haul_prompt_step == "galaxy_map_settle":
        parsed = parse_optional_nonnegative_float(
            app,
            value,
            default=float(
                app._haul_prompt_defaults.get(
                    "galaxy_map_settle",
                    app._config.controls.galaxy_map_settle_seconds,
                )
            ),
            label="Galaxy-map settle seconds",
        )
        if parsed is None:
            return
        app._haul_params["galaxy_map_settle"] = str(parsed)
        app._log(f"  Galaxy-map settle: [cyan]{parsed:.1f}s[/]")
        default_timeout = float(
            app._haul_prompt_defaults.get(
                "dock_timeout",
                app._config.controls.haul_dock_timeout_seconds,
            )
        )
        app._haul_prompt_step = "dock_timeout"
        app._log(f"[dim]Haul docking timeout seconds? (Enter = {default_timeout:.1f})[/]")
        app.query_one("#cmd", Input).placeholder = (
            f"haul docking timeout seconds (Enter = {default_timeout:.1f})..."
        )
        return

    if app._haul_prompt_step == "dock_timeout":
        parsed = parse_optional_nonnegative_float(
            app,
            value,
            default=float(
                app._haul_prompt_defaults.get(
                    "dock_timeout",
                    app._config.controls.haul_dock_timeout_seconds,
                )
            ),
            label="Haul docking timeout seconds",
        )
        if parsed is None:
            return
        app._haul_params["dock_timeout"] = str(parsed)
        app._log(f"  Haul docking timeout: [cyan]{parsed:.1f}s[/]")
        app._haul_prompt_step = ""
        app._haul_prompt_defaults = {}
        app.query_one("#cmd", Input).placeholder = default_placeholder
        app._dispatch_haul_loop(
            skip_delay=app._haul_prompt_skip_delay,
            raw_command=app._haul_prompt_raw_command,
        )


def parse_optional_nonnegative_float(
    app: PromptHost,
    raw: str,
    *,
    default: float,
    label: str,
) -> float | None:
    value = raw.strip()
    if not value:
        return default
    try:
        parsed = float(value)
    except ValueError:
        app._log(
            f"[red]{escape(error_text.render(app._config, 'number_required', label=label))}[/]"
        )
        return None
    if parsed < 0:
        app._log(
            f"[red]{escape(error_text.render(app._config, 'nonnegative_required', label=label))}[/]"
        )
        return None
    return parsed
