"""Navigation routine launchers (dest / set galaxy-map destination)."""
from __future__ import annotations

from rich.markup import escape

from edap.control_room.history import now_iso
from edap.control_room.interfaces import NavigationHost
from edap.control_room_state import CommandHistoryEntry
from edap.routines import set_gal_map_destination

def cmd_dest(
    app: NavigationHost,
    destination: str,
    *,
    skip_delay: bool = False,
    raw_command: str | None = None,
) -> None:
    if not app._check_routine_ready():
        return
    if not destination:
        app._log("[red]Usage: dest <system name>[/]")
        return
    app._start_dest_prompt(
        destination,
        skip_delay=skip_delay,
        raw_command=raw_command,
    )


def dispatch_dest(
    app: NavigationHost,
    destination: str,
    galaxy_map_settle: float,
    *,
    skip_delay: bool = False,
    raw_command: str | None = None,
) -> None:
    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    step_delay = app._config.controls.step_delay_seconds
    journal_dir = app._journal_dir

    app._record_history_entry(CommandHistoryEntry(
        raw=raw_command or f"{'!' if skip_delay else ''}dest {destination}",
        command="dest",
        params={
            "destination": destination,
            "galaxy_map_settle": galaxy_map_settle,
        },
        timestamp=now_iso(),
    ))
    app._start_delayed_routine(
        description=f"dest {destination}",
        start_message=(
            f"Setting galaxy map destination: [bold]{escape(destination)}[/] "
            f"[dim](settle {galaxy_map_settle:.1f}s)[/]"
        ),
        skip_delay=skip_delay,
        fn=lambda: set_gal_map_destination(
            controls,
            destination=destination,
            journal_dir=journal_dir,
            step_delay_s=step_delay,
            map_settle_s=galaxy_map_settle,
            sleeper=sleeper,
            progress_fn=progress,
        ),
    )
