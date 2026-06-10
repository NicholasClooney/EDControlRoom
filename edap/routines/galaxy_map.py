from __future__ import annotations

import json
from pathlib import Path
from time import monotonic, sleep
from typing import Callable

from edap.actions import ActionDispatchResult
from edap.routines._base import RoutineResult, SupportsGalaxyMapControls
from edap.routines._callbacks import ProgressCallback


def _read_navroute_destination(journal_dir: Path) -> str | None:
    navroute_path = journal_dir / "NavRoute.json"
    try:
        with navroute_path.open() as fh:
            data = json.load(fh)
        route = data.get("Route", [])
        if route:
            return str(route[-1].get("StarSystem", ""))
        return None
    except (OSError, json.JSONDecodeError):
        return None


def set_gal_map_destination(
    controls: SupportsGalaxyMapControls,
    *,
    destination: str,
    journal_dir: Path,
    open_check_fn: Callable[[], bool] | None = None,
    open_timeout_s: float = 10.0,
    open_settle_s: float = 5.0,
    search_settle_s: float = 2.0,
    map_settle_s: float = 2.0,
    step_delay_s: float = 0.5,
    search_commit_hold_s: float = 0.2,
    select_hold_s: float = 5.0,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: ProgressCallback,
) -> RoutineResult:
    """Odyssey galaxy map flow: open map, search by name, plot route, verify NavRoute."""

    def _err(action: str, reason: str, phase: str, **extra: object) -> RoutineResult:
        return RoutineResult(
            action=action,
            dispatch=ActionDispatchResult(action=action, status="error", reason=reason),
            details={"phase": phase, **extra},
        )

    # Step 1: open the galaxy map
    progress_fn("Opening galaxy map...")
    dispatch = controls.galaxy_map_open()
    if dispatch.status != "ok":
        return RoutineResult(action="GalaxyMapOpen", dispatch=dispatch, details={"phase": "open"})

    # Step 2: wait for map to be ready (OCR check or fixed settle)
    if open_check_fn is not None:
        progress_fn("Waiting for galaxy map (CARTOGRAPHICS check)...")
        deadline = time_fn() + open_timeout_s
        while time_fn() < deadline:
            if open_check_fn():
                break
            sleeper(0.5)
        else:
            progress_fn("Galaxy map open check timed out, proceeding anyway...")
    elif open_settle_s > 0:
        progress_fn(f"Waiting {open_settle_s:.1f}s for galaxy map to open...")
        sleeper(open_settle_s)

    # Step 3: navigate to search field (UI_Up + UI_Select)
    progress_fn("Navigating to search field...")
    dispatch = controls.ui_up()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Up", dispatch=dispatch, details={"phase": "navigate_to_search"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    dispatch = controls.ui_select()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Select", dispatch=dispatch, details={"phase": "navigate_to_search"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    # Step 4: type destination + held Enter to commit search
    progress_fn(f"Typing destination: {destination!r}")
    controls.type_text(destination)
    if step_delay_s > 0:
        sleeper(step_delay_s)

    progress_fn(f"Committing search (Enter held {search_commit_hold_s:.1f}s)...")
    dispatch = controls.submit_text(hold_s=search_commit_hold_s)
    if dispatch.status != "ok":
        return RoutineResult(action="Enter", dispatch=dispatch, details={"phase": "commit_search"})
    if search_settle_s > 0:
        progress_fn(f"Waiting {search_settle_s:.1f}s for search results to populate...")
        sleeper(search_settle_s)

    # Step 5: select the first result, then zoom/confirm plot
    progress_fn("Selecting result...")
    dispatch = controls.ui_right()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Right", dispatch=dispatch, details={"phase": "select_result"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    dispatch = controls.ui_select()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Select", dispatch=dispatch, details={"phase": "select_result"})
    if map_settle_s > 0:
        progress_fn(
            f"Waiting {map_settle_s:.1f}s for search result details to load "
            "(increase this for distant systems)..."
        )
        sleeper(map_settle_s)

    progress_fn("Zooming to plot route...")
    dispatch = controls.cam_zoom_in()
    if dispatch.status != "ok":
        return RoutineResult(action="CamZoomIn", dispatch=dispatch, details={"phase": "prepare_plot"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    progress_fn(f"Plotting route (UI_Select held {select_hold_s:.1f}s)...")
    plot_dispatch = controls.ui_select(hold_s=select_hold_s)
    if plot_dispatch.status != "ok":
        return RoutineResult(action="UI_Select", dispatch=plot_dispatch, details={"phase": "plot_route"})
    if map_settle_s > 0:
        progress_fn(
            f"Waiting {map_settle_s:.1f}s for route plot to settle "
            "(increase this for distant systems)..."
        )
        sleeper(map_settle_s)

    # Step 6: verify NavRoute.json
    actual = _read_navroute_destination(journal_dir)
    if actual is None or actual.lower() != destination.lower():
        got = actual or "unknown"
        progress_fn(f"Route mismatch: expected {destination!r}, got {got!r}")
        controls.galaxy_map_open()
        return _err("GalaxyMapOpen", f"route mismatch: expected {destination!r}, got {got!r}", "verify_route", destination=destination, actual=got)

    progress_fn(f"Route set to {actual!r}")

    # Step 7: close the galaxy map
    progress_fn("Closing galaxy map...")
    controls.galaxy_map_open()
    return RoutineResult(
        action="GalaxyMapOpen",
        dispatch=plot_dispatch,
        details={"destination": destination, "actual": actual},
    )
