"""Movement routine launchers (jump, escape mass lock, boost)."""
from __future__ import annotations

from edap.control_room.interfaces import RoutineHost
from edap.routines import RoutineResult, escape_mass_lock, jump

def cmd_jump(app: RoutineHost, *, skip_delay: bool = False) -> None:
    if not app._check_routine_ready():
        return
    progress = app._make_progress()
    controls = app._make_controls(progress)
    watcher = app._make_watcher()

    app._start_delayed_routine(
        description="jump",
        start_message="Starting jump sequence...",
        skip_delay=skip_delay,
        fn=lambda: jump(
            controls,
            watcher,
            progress_fn=progress,
        ),
    )


def cmd_escape(app: RoutineHost, *, skip_delay: bool = False) -> None:
    if not app._check_routine_ready():
        return
    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    journal_dir = app._journal_dir
    boost_delay = app._config.controls.mass_lock_boost_delay_seconds
    step_delay = app._config.controls.step_delay_seconds

    app._start_delayed_routine(
        description="escape",
        start_message="Starting escape mass lock...",
        skip_delay=skip_delay,
        fn=lambda: escape_mass_lock(
            controls,
            journal_dir=journal_dir,
            boost_delay_s=boost_delay,
            step_delay_s=step_delay,
            sleeper=sleeper,
            progress_fn=progress,
        ),
    )


def cmd_boost(app: RoutineHost, *, skip_delay: bool = False) -> None:
    if not app._check_routine_ready():
        return
    progress = app._make_progress()
    controls = app._make_controls(progress)

    def run_boost() -> RoutineResult:
        result = controls.boost(repeat=3)
        return RoutineResult(
            action="Boost",
            dispatch=result,
            details={"boost_count": 3},
        )

    app._start_delayed_routine(
        description="boost",
        start_message="Boosting 3x...",
        skip_delay=skip_delay,
        fn=run_boost,
    )
