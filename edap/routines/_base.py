from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable, Protocol

from edap.actions import ActionDispatchResult


class SupportsSetSpeedZero(Protocol):
    def set_speed_zero(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the SetSpeedZero action."""


class SupportsJumpControls(SupportsSetSpeedZero, Protocol):
    def hyper_super_combination(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the HyperSuperCombination action."""


class SupportsPollEvents(Protocol):
    def poll(self) -> list[dict[str, object]]:
        """Return newly observed journal events."""


class SupportsStationMenuControls(Protocol):
    def ui_up(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Up action."""

    def ui_select(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Select action."""

    def ui_down(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Down action."""


class SupportsUndockControls(Protocol):
    def ui_back(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Back action."""

    def head_look_reset(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the HeadLookReset action."""

    def ui_down(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Down action."""

    def ui_select(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Select action."""


class SupportsMarketControls(Protocol):
    def ui_select(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Select action."""

    def ui_down(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Down action."""

    def ui_right(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Right action."""

    def ui_back(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Back action."""


class SupportsDockingControls(SupportsStationMenuControls, SupportsSetSpeedZero, Protocol):
    def boost(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the BoostButton action."""

    def focus_left_panel(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the FocusLeftPanel action."""

    def ui_back(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Back action."""

    def cycle_next_panel(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the CycleNextPanel action."""

    def cycle_previous_panel(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the CyclePreviousPanel action."""

    def ui_right(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Right action."""

    def ui_left(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Left action."""


class SupportsGalaxyMapControls(Protocol):
    def galaxy_map_open(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the GalaxyMapOpen action."""

    def ui_up(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Up action."""

    def ui_down(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Down action."""

    def ui_select(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Select action."""

    def ui_right(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the UI_Right action."""

    def cam_zoom_in(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        """Dispatch the CamZoomIn action."""

    def type_text(self, text: str) -> None:
        """Type a string of text character by character."""


class SupportsHaulControls(SupportsDockingControls, SupportsUndockControls, SupportsMarketControls, SupportsGalaxyMapControls, Protocol):
    """Combined protocol for all controls needed in the haul loop."""


@dataclass(frozen=True)
class RoutineResult:
    action: str
    dispatch: ActionDispatchResult
    wait_s: float = 0.0
    trigger_event: dict[str, object] | None = None
    details: dict[str, object] | None = None


def _wait_for_event(
    watcher: SupportsPollEvents,
    *,
    predicate: Callable[[dict[str, object]], bool],
    deadline: float,
    time_fn: Callable[[], float],
) -> dict[str, object] | None:
    while time_fn() <= deadline:
        for event in watcher.poll():
            if predicate(event):
                return event
    return None


def _is_starting_hyperspace_event(event: dict[str, object]) -> bool:
    return event.get("event") == "StartJump" and str(event.get("JumpType", "")).lower() == "hyperspace"


def _is_in_supercruise_event(event: dict[str, object]) -> bool:
    return event.get("event") in {"SupercruiseEntry", "FSDJump"}


def _is_supercruise_exit_event(event: dict[str, object]) -> bool:
    return event.get("event") == "SupercruiseExit"


def _is_docking_started_event(event: dict[str, object]) -> bool:
    return event.get("event") in {"DockingRequested", "DockingGranted"}


def _is_docking_response_event(event: dict[str, object]) -> bool:
    return event.get("event") in {"DockingRequested", "DockingGranted", "DockingDenied"}


def _is_docked_event(event: dict[str, object]) -> bool:
    return event.get("event") == "Docked"


def _is_undocked_event(event: dict[str, object]) -> bool:
    return event.get("event") == "Undocked"
