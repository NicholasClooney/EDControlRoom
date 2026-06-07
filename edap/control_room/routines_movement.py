"""Movement routine launchers (jump, escape mass lock, boost)."""
from __future__ import annotations

from edap.control_room.interfaces import RoutineHost
from edap.routines import RoutineResult, escape_mass_lock, jump

def cmd_jump(app: RoutineHost) -> None:
    if not app._check_routine_ready():
        return
    progress = app._make_progress()
    controls = app._make_controls(progress)
    watcher = app._make_watcher()

    app._routine_active = True
    app._log("Starting jump sequence...")
    app._routine_worker = app._run_in_thread(lambda: jump(
        controls,
        watcher,
        progress_fn=progress,
    ))


def cmd_escape(app: RoutineHost) -> None:
    if not app._check_routine_ready():
        return
    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    journal_dir = app._journal_dir
    boost_delay = app._config.controls.mass_lock_boost_delay_seconds
    step_delay = app._config.controls.step_delay_seconds

    app._routine_active = True
    app._log("Starting escape mass lock...")
    app._routine_worker = app._run_in_thread(lambda: escape_mass_lock(
        controls,
        journal_dir=journal_dir,
        boost_delay_s=boost_delay,
        step_delay_s=step_delay,
        sleeper=sleeper,
        progress_fn=progress,
    ))


def cmd_boost(app: RoutineHost) -> None:
    if not app._check_routine_ready():
        return
    progress = app._make_progress()
    controls = app._make_controls(progress)

    app._routine_active = True
    app._log("Boosting 3x...")

    def run_boost() -> RoutineResult:
        result = controls.boost(repeat=3)
        return RoutineResult(
            action="Boost",
            dispatch=result,
            details={"boost_count": 3},
        )

    app._routine_worker = app._run_in_thread(run_boost)
