"""Haul-loop routine launcher (cmd_haul, dispatch_haul_loop)."""
from __future__ import annotations

import re

from rich.markup import escape

from edap.control_room.history import now_iso
from edap.control_room.interfaces import HaulHost
from edap.control_room_state import CommandHistoryEntry
from edap.routines import haul_loop
from edap.routines.haul import _detect_phase


_CONFIRM_STATION_RE = re.compile(r"^Assume current station (.+) is the buy station\?$")


def _station_from_confirmation_prompt(prompt: str) -> str:
    match = _CONFIRM_STATION_RE.match(prompt)
    if match is None:
        return ""
    raw_station = match.group(1)
    if len(raw_station) >= 2 and raw_station[0] == raw_station[-1] and raw_station[0] in {"'", '"'}:
        return raw_station[1:-1]
    return raw_station


def cmd_haul(
    app: HaulHost,
    rest: str,
    *,
    skip_delay: bool = False,
    raw_command: str | None = None,
) -> None:
    if not app._check_routine_ready():
        return
    commodity = rest.strip()
    if not commodity:
        app._start_haul_prompt(
            commodity="",
            prompt_for_commodity=True,
            skip_delay=skip_delay,
            raw_command=raw_command,
        )
    else:
        app._start_haul_prompt(
            commodity=commodity,
            prompt_for_commodity=False,
            skip_delay=skip_delay,
            raw_command=raw_command,
        )


def dispatch_haul_loop(
    app: HaulHost,
    *,
    skip_delay: bool = False,
    raw_command: str | None = None,
) -> None:
    commodity = app._haul_params.get("commodity", "")
    buy_station = app._haul_params.get("buy_station", "")
    sell_station = app._haul_params.get("sell_station", "")
    sell_system = app._haul_params.get("sell_system", "")
    buy_system = app._haul_params.get("buy_system", "")
    galaxy_map_settle_raw = app._haul_params.get("galaxy_map_settle", "")
    dock_timeout_raw = app._haul_params.get("dock_timeout", "")

    if not sell_station and app._ship.station:
        sell_station = app._ship.station
        app._log(f"[dim]Sell station defaulting to current station: [cyan]{escape(sell_station)}[/][/]")
    elif sell_station and app._ship.status == "in_station" and app._ship.station:
        if app._ship.station.lower() != sell_station.lower():
            app._log(
                f"[yellow]Warning: docked at [bold]{escape(app._ship.station)}[/bold] "
                f"but sell station is [bold]{escape(sell_station)}[/bold]. "
                f"Haul resume detection will use the configured stations and cargo state.[/]"
            )

    if not sell_system and app._ship.system:
        sell_system = app._ship.system
        app._log(f"[dim]Sell system defaulting to current system: [cyan]{escape(sell_system)}[/][/]")

    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    step_delay = app._config.controls.step_delay_seconds
    galaxy_map_settle = (
        float(galaxy_map_settle_raw)
        if galaxy_map_settle_raw
        else app._config.controls.galaxy_map_settle_seconds
    )
    dock_timeout = (
        float(dock_timeout_raw)
        if dock_timeout_raw
        else app._config.controls.haul_dock_timeout_seconds
    )
    journal_dir = app._journal_dir
    watcher = app._make_watcher()

    confirmation_prompts: list[str] = []
    try:
        _detect_phase(
            journal_dir,
            sell_station=sell_station,
            buy_station=buy_station,
            sell_system=sell_system,
            buy_system=buy_system,
            commodity=commodity,
            confirm_fn=lambda message: confirmation_prompts.append(message) or False,
        )
    except RuntimeError as exc:
        if confirmation_prompts:
            station = _station_from_confirmation_prompt(confirmation_prompts[0])
            if station:
                app._start_haul_confirm_prompt(station)
                return
        app._log(f"[red]{escape(str(exc))}[/]")
        return

    app._record_history_entry(CommandHistoryEntry(
        raw=raw_command or f"{'!' if skip_delay else ''}haul {commodity}",
        command="haul",
        params={
            "commodity": commodity,
            "buy_station": buy_station,
            "sell_station": sell_station,
            "sell_system": sell_system,
            "buy_system": buy_system,
            "galaxy_map_settle": str(galaxy_map_settle),
            "dock_timeout": str(dock_timeout),
        },
        timestamp=now_iso(),
    ))

    label_parts = [f"[cyan]{escape(commodity)}[/]"]
    if buy_station:
        label_parts.append(f"buy @ [cyan]{escape(buy_station)}[/]")
    if sell_station:
        label_parts.append(f"sell @ [cyan]{escape(sell_station)}[/]")
    if buy_system:
        label_parts.append(f"buy sys: [cyan]{escape(buy_system)}[/]")
    if sell_system:
        label_parts.append(f"sell sys: [cyan]{escape(sell_system)}[/]")
    label_parts.append(f"map settle: [cyan]{galaxy_map_settle:.1f}s[/]")
    label_parts.append(f"dock timeout: [cyan]{dock_timeout:.1f}s[/]")

    def on_start() -> None:
        app._log(f"Starting haul loop: {', '.join(label_parts)} (infinite)...")
        app._start_haul_stats(
            commodity=commodity,
            buy_station=buy_station,
            sell_station=sell_station,
        )

    app._start_delayed_routine(
        description=f"haul {commodity}",
        start_message="",
        skip_delay=skip_delay,
        fn=lambda: haul_loop(
            controls,
            watcher,
            journal_dir=journal_dir,
            commodity=commodity,
            buy_station=buy_station,
            sell_station=sell_station,
            sell_system=sell_system,
            buy_system=buy_system,
            step_delay_s=step_delay,
            dock_timeout_s=dock_timeout,
            galaxy_map_settle_s=galaxy_map_settle,
            mass_lock_boost_delay_s=app._config.controls.mass_lock_boost_delay_seconds,
            sleeper=sleeper,
            progress_fn=progress,
            confirm_fn=lambda _: False,
        ),
        active_routine_name="haul",
        on_start=on_start,
    )
