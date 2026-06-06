from __future__ import annotations

from typing import Callable

from edap.actions import ActionDispatchResult
from edap.ship_controls import ShipControls


class ProgressShipControls:
    """Wraps ShipControls to route each key dispatch through a progress function.

    When verbose=True each key press is emitted via progress_fn before dispatch.
    When verbose=False (default) the wrapper is a transparent passthrough and
    progress_fn is never called for key presses — only for routine-level messages
    passed directly by the caller.
    """

    def __init__(
        self,
        controls: ShipControls,
        progress_fn: Callable[[str], None],
        *,
        verbose: bool = False,
    ) -> None:
        self._controls = controls
        self._progress = progress_fn
        self._verbose = verbose

    def _log(self, action: str, repeat: int) -> None:
        if not self._verbose:
            return
        suffix = f" x{repeat}" if repeat > 1 else ""
        self._progress(f"  key: {action}{suffix}")

    def set_speed_zero(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("SetSpeedZero", repeat)
        return self._controls.set_speed_zero(repeat=repeat, hold_s=hold_s)

    def boost(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("BoostButton", repeat)
        return self._controls.boost(repeat=repeat, hold_s=hold_s)

    def hyper_super_combination(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("HyperSuperCombination", repeat)
        return self._controls.hyper_super_combination(repeat=repeat, hold_s=hold_s)

    def focus_left_panel(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("FocusLeftPanel", repeat)
        return self._controls.focus_left_panel(repeat=repeat, hold_s=hold_s)

    def ui_back(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("UI_Back", repeat)
        return self._controls.ui_back(repeat=repeat, hold_s=hold_s)

    def cycle_next_panel(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("CycleNextPanel", repeat)
        return self._controls.cycle_next_panel(repeat=repeat, hold_s=hold_s)

    def cycle_previous_panel(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("CyclePreviousPanel", repeat)
        return self._controls.cycle_previous_panel(repeat=repeat, hold_s=hold_s)

    def ui_right(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("UI_Right", repeat)
        return self._controls.ui_right(repeat=repeat, hold_s=hold_s)

    def ui_left(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("UI_Left", repeat)
        return self._controls.ui_left(repeat=repeat, hold_s=hold_s)

    def ui_up(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("UI_Up", repeat)
        return self._controls.ui_up(repeat=repeat, hold_s=hold_s)

    def ui_select(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("UI_Select", repeat)
        return self._controls.ui_select(repeat=repeat, hold_s=hold_s)

    def ui_down(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("UI_Down", repeat)
        return self._controls.ui_down(repeat=repeat, hold_s=hold_s)

    def head_look_reset(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("HeadLookReset", repeat)
        return self._controls.head_look_reset(repeat=repeat, hold_s=hold_s)

    def galaxy_map_open(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("GalaxyMapOpen", repeat)
        return self._controls.galaxy_map_open(repeat=repeat, hold_s=hold_s)

    def cam_zoom_in(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        self._log("CamZoomIn", repeat)
        return self._controls.cam_zoom_in(repeat=repeat, hold_s=hold_s)

    def type_text(self, text: str) -> None:
        if self._verbose:
            self._progress(f"  type_text: {text!r}")
        self._controls.type_text(text)
