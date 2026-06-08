"""Station routine launchers (dock, undock)."""
from __future__ import annotations

from edap.control_room.interfaces import RoutineHost
from edap.routines import dock, undock

def cmd_dock(app: RoutineHost, *, skip_delay: bool = False) -> None:
    if not app._check_routine_ready():
        return
    skip_scx = app._ship.status == "in_space"
    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    step_delay = app._config.controls.step_delay_seconds
    supercruise_exit_settle = app._config.controls.dock_supercruise_exit_settle_seconds
    watcher = app._make_watcher()

    label = "dock (already in space)" if skip_scx else "dock (waiting for supercruise exit)"
    app._start_delayed_routine(
        description=label,
        start_message=f"Starting {label}, auto-refuel on...",
        skip_delay=skip_delay,
        fn=lambda: dock(
            controls,
            watcher,
            wait_for_supercruise_exit=not skip_scx,
            auto_refuel=True,
            step_delay_s=step_delay,
            supercruise_exit_settle_s=supercruise_exit_settle,
            sleeper=sleeper,
            progress_fn=progress,
            announce_fn=app._announce_tts,
            announce_station_name=app._ship.station or "",
        ),
    )


def cmd_undock(app: RoutineHost, *, skip_delay: bool = False) -> None:
    if not app._check_routine_ready():
        return
    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    step_delay = app._config.controls.step_delay_seconds
    undock_timeout = app._config.controls.undock_timeout_seconds
    no_track_timeout = app._config.controls.undock_no_track_timeout_seconds
    watcher = app._make_watcher()

    app._start_delayed_routine(
        description="undock",
        start_message="Starting undock...",
        skip_delay=skip_delay,
        fn=lambda: undock(
            controls,
            watcher,
            undock_timeout_s=undock_timeout,
            no_track_timeout_s=no_track_timeout,
            step_delay_s=step_delay,
            sleeper=sleeper,
            progress_fn=progress,
        ),
    )
