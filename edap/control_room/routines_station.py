"""Station routine launchers (dock, undock).

Tightly coupled to ControlRoomApp — split for file size.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from edap.routines import dock, undock

if TYPE_CHECKING:
    from control_room import ControlRoomApp


def cmd_dock(app: ControlRoomApp) -> None:
    if not app._check_routine_ready():
        return
    skip_scx = app._ship.status == "in_space"
    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    step_delay = app._config.controls.step_delay_seconds
    watcher = app._make_watcher()

    app._routine_active = True
    label = "dock (already in space)" if skip_scx else "dock (waiting for supercruise exit)"
    app._log(f"Starting {label}, auto-refuel on...")
    app._routine_worker = app._run_in_thread(lambda: dock(
        controls,
        watcher,
        wait_for_supercruise_exit=not skip_scx,
        auto_refuel=True,
        step_delay_s=step_delay,
        sleeper=sleeper,
        progress_fn=progress,
    ))


def cmd_undock(app: ControlRoomApp) -> None:
    if not app._check_routine_ready():
        return
    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    step_delay = app._config.controls.step_delay_seconds
    undock_timeout = app._config.controls.undock_timeout_seconds
    watcher = app._make_watcher()

    app._routine_active = True
    app._log("Starting undock...")
    app._routine_worker = app._run_in_thread(lambda: undock(
        controls,
        watcher,
        undock_timeout_s=undock_timeout,
        step_delay_s=step_delay,
        sleeper=sleeper,
        progress_fn=progress,
    ))
