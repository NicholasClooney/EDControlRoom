"""Haul routine launchers."""
from __future__ import annotations

from rich.markup import escape

from edap.control_room import error_text
from edap.control_room.history import now_iso
from edap.control_room.interfaces import HaulHost
from edap.control_room_state import CommandHistoryEntry
from edap.multi_leg_haul import load_multi_leg_haul_definition
from edap.routines import haul_loop_two_way, multi_leg_haul


def cmd_haul(
    app: HaulHost,
    rest: str,
    *,
    skip_delay: bool = False,
    raw_command: str | None = None,
) -> None:
    if not app._check_routine_ready():
        return
    station_1_buying = rest.strip()
    if not station_1_buying:
        app._start_haul_prompt(
            commodity="",
            prompt_for_commodity=True,
            skip_delay=skip_delay,
            raw_command=raw_command,
        )
    else:
        app._start_haul_prompt(
            commodity=station_1_buying,
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
    station_1_buying = app._haul_params.get("station_1_buying", "")
    station_1 = app._haul_params.get("station_1", "")
    station_1_system = app._haul_params.get("station_1_system", "")
    station_2_buying = app._haul_params.get("station_2_buying", "")
    station_2 = app._haul_params.get("station_2", "")
    station_2_system = app._haul_params.get("station_2_system", "")
    galaxy_map_settle_raw = app._haul_params.get("galaxy_map_settle", "")
    dock_timeout_raw = app._haul_params.get("dock_timeout", "")

    if not station_1 and app._ship.station:
        station_1 = app._ship.station
        app._log(f"[dim]Station 1 defaulting to current station: [cyan]{escape(station_1)}[/][/]")
    if not station_1_system and app._ship.system:
        station_1_system = app._ship.system
        app._log(f"[dim]Station 1 system defaulting to current system: [cyan]{escape(station_1_system)}[/][/]")
    if not station_1_buying or not station_2_buying or not station_1 or not station_2 or not station_2_system:
        app._log(f"[red]{escape(error_text.render(app._config, 'haul_params_required'))}[/]")
        return

    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    step_delay = app._config.controls.step_delay_seconds
    undock_timeout = app._config.controls.undock_timeout_seconds
    undock_no_track_timeout = app._config.controls.undock_no_track_timeout_seconds
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
    app._clear_pending_haul_stop()

    app._record_history_entry(CommandHistoryEntry(
        raw=raw_command or f"{'!' if skip_delay else ''}haul {station_1_buying}",
        command="haul",
        params={
            "station_1_buying": station_1_buying,
            "station_1": station_1,
            "station_1_system": station_1_system,
            "station_2_buying": station_2_buying,
            "station_2": station_2,
            "station_2_system": station_2_system,
            "galaxy_map_settle": str(galaxy_map_settle),
            "dock_timeout": str(dock_timeout),
        },
        timestamp=now_iso(),
    ))

    label_parts = [
        f"station 1 [cyan]{escape(station_1)}[/]: buy [cyan]{escape(station_1_buying)}[/]",
        f"station 2 [cyan]{escape(station_2)}[/]: buy [cyan]{escape(station_2_buying)}[/]",
    ]
    if station_1_system:
        label_parts.append(f"station 1 sys: [cyan]{escape(station_1_system)}[/]")
    if station_2_system:
        label_parts.append(f"station 2 sys: [cyan]{escape(station_2_system)}[/]")
    label_parts.append(f"map settle: [cyan]{galaxy_map_settle:.1f}s[/]")
    label_parts.append(f"dock timeout: [cyan]{dock_timeout:.1f}s[/]")

    def on_start() -> None:
        app._log(f"Starting haul loop: {', '.join(label_parts)} (infinite)...")
        app._start_haul_stats(
            station_1_buying=station_1_buying,
            station_2_buying=station_2_buying,
            station_1=station_1,
            station_2=station_2,
        )

    app._start_delayed_routine(
        description=f"haul {station_1_buying}",
        start_message="",
        skip_delay=skip_delay,
        fn=lambda: haul_loop_two_way(
            controls,
            watcher,
            journal_dir=journal_dir,
            station_1=station_1,
            station_1_buying=station_1_buying,
            station_1_system=station_1_system,
            station_2=station_2,
            station_2_buying=station_2_buying,
            station_2_system=station_2_system,
            step_delay_s=step_delay,
            dock_timeout_s=dock_timeout,
            undock_timeout_s=undock_timeout,
            undock_no_track_timeout_s=undock_no_track_timeout,
            galaxy_map_settle_s=galaxy_map_settle,
            supercruise_exit_settle_s=app._config.controls.dock_supercruise_exit_settle_seconds,
            mass_lock_boost_delay_s=app._config.controls.mass_lock_boost_delay_seconds,
            post_sell_settle_s=app._config.controls.haul_post_sell_settle_seconds,
            auto_hyperspace_engage=app._config.controls.haul_two_way_auto_hyperspace_engage,
            open_nav_panel_after_hyperspace_arrival=(
                app._config.controls.haul_two_way_open_nav_panel_after_hyperspace_arrival
            ),
            nav_panel_open_delay_s=app._config.controls.haul_two_way_nav_panel_open_delay_seconds,
            market_buy_hold_seconds_per_ton=app._config.controls.market_buy_hold_seconds_per_ton,
            market_critical_level_multiplier=app._config.controls.market_critical_level_multiplier,
            sleeper=sleeper,
            progress_fn=progress,
            announce_fn=app._announce_tts,
            stop_requested_fn=lambda: app._haul_stop_requested,
        ),
        active_routine_name="haul",
        on_start=on_start,
    )


def cmd_multi_leg_haul(
    app: HaulHost,
    rest: str,
    *,
    skip_delay: bool = False,
    raw_command: str | None = None,
) -> None:
    if not app._check_routine_ready():
        return
    source = rest.strip()
    if not source:
        app._log("[red]Usage: multi_leg_haul <route.json | spansh-url>[/]")
        return
    dispatch_multi_leg_haul(
        app,
        source=source,
        skip_delay=skip_delay,
        raw_command=raw_command,
    )


def dispatch_multi_leg_haul(
    app: HaulHost,
    *,
    source: str,
    skip_delay: bool = False,
    raw_command: str | None = None,
) -> None:
    try:
        definition = load_multi_leg_haul_definition(source)
    except Exception as exc:
        app._log(f"[red]Failed to load multi-leg haul source: {escape(str(exc))}[/]")
        return

    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    watcher = app._make_watcher()
    app._clear_pending_haul_stop()
    app._record_history_entry(CommandHistoryEntry(
        raw=raw_command or f"{'!' if skip_delay else ''}multi_leg_haul {source}",
        command="multi_leg_haul",
        params={"source": source},
        timestamp=now_iso(),
    ))

    route_label = f"{definition.route_name} ({definition.total_legs} legs)"
    route_source = definition.source_provider or "json"

    def on_start() -> None:
        app._stop_haul_stats()
        app._log(
            "Starting multi-leg haul: "
            f"[cyan]{escape(route_label)}[/] from [cyan]{escape(route_source)}[/]"
        )

    app._start_delayed_routine(
        description=f"multi_leg_haul {source}",
        start_message="",
        skip_delay=skip_delay,
        fn=lambda: multi_leg_haul(
            controls,
            watcher,
            definition=definition,
            journal_dir=app._journal_dir,
            step_delay_s=app._config.controls.step_delay_seconds,
            dock_timeout_s=app._config.controls.haul_dock_timeout_seconds,
            undock_timeout_s=app._config.controls.undock_timeout_seconds,
            undock_no_track_timeout_s=app._config.controls.undock_no_track_timeout_seconds,
            request_timeout_s=20.0,
            galaxy_map_settle_s=app._config.controls.galaxy_map_settle_seconds,
            supercruise_exit_settle_s=app._config.controls.dock_supercruise_exit_settle_seconds,
            mass_lock_boost_delay_s=app._config.controls.mass_lock_boost_delay_seconds,
            post_sell_settle_s=app._config.controls.haul_post_sell_settle_seconds,
            auto_hyperspace_engage=app._config.controls.haul_two_way_auto_hyperspace_engage,
            open_nav_panel_after_hyperspace_arrival=(
                app._config.controls.haul_two_way_open_nav_panel_after_hyperspace_arrival
            ),
            nav_panel_open_delay_s=app._config.controls.haul_two_way_nav_panel_open_delay_seconds,
            market_buy_hold_seconds_per_ton=app._config.controls.market_buy_hold_seconds_per_ton,
            market_critical_level_multiplier=app._config.controls.market_critical_level_multiplier,
            sleeper=sleeper,
            progress_fn=progress,
            announce_fn=app._announce_tts,
            stop_requested_fn=lambda: app._haul_stop_requested,
        ),
        active_routine_name="multi_leg_haul",
        on_start=on_start,
    )
