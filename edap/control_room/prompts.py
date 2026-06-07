from __future__ import annotations

from typing import Protocol

from rich.markup import escape
from textual.widgets import Input

from edap.config import AppConfig
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
    _dest_prompt_destination: str
    _dest_prompt_settle_default: float | None

    def _log(self, msg: str) -> None: ...
    def _dispatch_haul_loop(self) -> None: ...
    def _dispatch_dest(self, destination: str, galaxy_map_settle: float) -> None: ...
    def query_one(self, selector: str, widget_type: type[Input]) -> Input: ...


def start_dest_prompt(
    app: PromptHost,
    destination: str,
    *,
    settle_default: float | None = None,
) -> None:
    app._dest_prompt_destination = destination
    app._dest_prompt_settle_default = (
        settle_default
        if settle_default is not None
        else app._config.controls.galaxy_map_settle_seconds
    )
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
    if not defaults.get("sell_station") and app._ship.station:
        defaults["sell_station"] = app._ship.station
    if not defaults.get("sell_system") and app._ship.system:
        defaults["sell_system"] = app._ship.system
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
) -> None:
    app._haul_params = {
        "commodity": commodity.strip(),
        "buy_station": "",
        "sell_station": "",
        "sell_system": "",
        "buy_system": "",
        "galaxy_map_settle": "",
        "dock_timeout": "",
    }
    app._haul_prompt_defaults = saved_haul_defaults(app, seed)
    app._log("Haul loop setup — enter parameters below:")
    if prompt_for_commodity:
        app._haul_prompt_step = "commodity"
        default_commodity = app._haul_prompt_defaults.get("commodity", "")
        if default_commodity:
            app._log(f"[dim]Commodity to buy? (Enter = {escape(default_commodity)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"commodity (Enter = {default_commodity})..."
            )
        else:
            app._log("[dim]Commodity to buy? (e.g. Aluminium)[/]")
            app.query_one("#cmd", Input).placeholder = "commodity..."
        return

    app._log(f"Haul loop: commodity = [cyan]{escape(app._haul_params['commodity'])}[/]")
    app._haul_prompt_step = "buy_station"
    default_buy_station = app._haul_prompt_defaults.get("buy_station", "")
    if default_buy_station:
        app._log(f"[dim]Buy station name? (Enter = {escape(default_buy_station)})[/]")
        app.query_one("#cmd", Input).placeholder = (
            f"buy station (Enter = {default_buy_station})..."
        )
    else:
        app._log("[dim]Buy station name? (press Enter to skip)[/]")
        app.query_one("#cmd", Input).placeholder = "buy station (Enter to skip)..."


def start_haul_confirm_prompt(
    app: PromptHost,
    station: str,
) -> None:
    app._haul_confirm_buy_station = station
    app._log(
        f"[dim]Assume current station [cyan]{escape(station)}[/] is the buy station? "
        f"(Enter = yes, no to cancel)[/]"
    )
    app.query_one("#cmd", Input).placeholder = (
        "confirm buy station? Enter = yes, no to cancel..."
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
        app._haul_params["buy_station"] = station
        app._log(f"  Buy station confirmed: [cyan]{escape(station)}[/]")
        app.query_one("#cmd", Input).placeholder = default_placeholder
        app._dispatch_haul_loop()
        return
    if answer in {"n", "no"}:
        station = app._haul_confirm_buy_station
        app._haul_confirm_buy_station = ""
        app._log(
            f"[yellow]Haul launch cancelled — buy station left unresolved "
            f"for [cyan]{escape(station)}[/].[/]"
        )
        app.query_one("#cmd", Input).placeholder = default_placeholder
        return
    app._log("[red]Press Enter for yes, or type no to cancel.[/]")


def handle_haul_prompt(
    app: PromptHost,
    value: str,
    *,
    default_placeholder: str,
) -> None:
    if app._haul_prompt_step == "commodity":
        resolved = value.strip() or app._haul_prompt_defaults.get("commodity", "")
        if not resolved:
            app._log("[red]Commodity is required — enter a commodity name.[/]")
            return
        app._haul_params["commodity"] = resolved
        app._log(f"  Commodity: [cyan]{escape(resolved)}[/]")
        app._haul_prompt_step = "buy_station"
        default_buy_station = app._haul_prompt_defaults.get("buy_station", "")
        if default_buy_station:
            app._log(f"[dim]Buy station name? (Enter = {escape(default_buy_station)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"buy station (Enter = {default_buy_station})..."
            )
        else:
            app._log("[dim]Buy station name? (press Enter to skip)[/]")
            app.query_one("#cmd", Input).placeholder = "buy station (Enter to skip)..."
        return

    if app._haul_prompt_step == "buy_station":
        resolved = value.strip() or app._haul_prompt_defaults.get("buy_station", "")
        app._haul_params["buy_station"] = resolved
        if resolved:
            app._log(f"  Buy station: [cyan]{escape(resolved)}[/]")
        else:
            app._log("  Buy station: [dim](none)[/]")
        app._haul_prompt_step = "sell_station"
        default_sell_station = app._haul_prompt_defaults.get("sell_station", "")
        if default_sell_station:
            app._log(f"[dim]Sell station name? (Enter = {escape(default_sell_station)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"sell station (Enter = {default_sell_station})..."
            )
        else:
            current = app._ship.station or "current station"
            app._log(f"[dim]Sell station name? (Enter to use {escape(current)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"sell station (Enter = {current})..."
            )
        return

    if app._haul_prompt_step == "sell_station":
        resolved = value.strip() or app._haul_prompt_defaults.get("sell_station", "")
        app._haul_params["sell_station"] = resolved
        if resolved:
            app._log(f"  Sell station: [cyan]{escape(resolved)}[/]")
        else:
            app._log("  Sell station: [dim](current station)[/]")
        app._haul_prompt_step = "sell_system"
        default_sell_system = app._haul_prompt_defaults.get("sell_system", "")
        if default_sell_system:
            app._log(f"[dim]Sell system? (Enter = {escape(default_sell_system)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"sell system (Enter = {default_sell_system})..."
            )
        else:
            current_system = app._ship.system or "current system"
            app._log(f"[dim]Sell system? (Enter to use {escape(current_system)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"sell system (Enter = {current_system})..."
            )
        return

    if app._haul_prompt_step == "sell_system":
        resolved = value.strip() or app._haul_prompt_defaults.get("sell_system", "")
        app._haul_params["sell_system"] = resolved
        if resolved:
            app._log(f"  Sell system: [cyan]{escape(resolved)}[/]")
        else:
            app._log("  Sell system: [dim](current system)[/]")
        app._haul_prompt_step = "buy_system"
        default_buy_system = app._haul_prompt_defaults.get("buy_system", "")
        if default_buy_system:
            app._log(f"[dim]Buy system? (Enter = {escape(default_buy_system)})[/]")
            app.query_one("#cmd", Input).placeholder = (
                f"buy system (Enter = {default_buy_system})..."
            )
        else:
            app._log("[dim]Buy system? (press Enter to skip)[/]")
            app.query_one("#cmd", Input).placeholder = "buy system (Enter to skip)..."
        return

    if app._haul_prompt_step == "buy_system":
        resolved = value.strip() or app._haul_prompt_defaults.get("buy_system", "")
        app._haul_params["buy_system"] = resolved
        if resolved:
            app._log(f"  Buy system: [cyan]{escape(resolved)}[/]")
        else:
            app._log("  Buy system: [dim](none)[/]")
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
        app._dispatch_haul_loop()


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
        app._log(f"[red]{escape(label)} must be a number.[/]")
        return None
    if parsed < 0:
        app._log(f"[red]{escape(label)} must be non-negative.[/]")
        return None
    return parsed
