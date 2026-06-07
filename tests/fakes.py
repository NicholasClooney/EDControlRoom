from __future__ import annotations

from edap.actions import ActionDispatchResult
from edap.binding_lookup import NormalizedBinding

_OK = ActionDispatchResult(action="ok", status="ok", binding=NormalizedBinding(key="x", modifier=None))


class FakeShipControls:
    def __init__(
        self,
        *,
        set_speed_zero_result: ActionDispatchResult = _OK,
        jump_result: ActionDispatchResult | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._set_speed_zero_result = set_speed_zero_result
        self._jump_result = jump_result or set_speed_zero_result

    def _dispatch(self, action: str, repeat: int, hold_s: float) -> ActionDispatchResult:
        self.calls.append({"action": action, "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def set_speed_zero(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "SetSpeedZero", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def hyper_super_combination(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "HyperSuperCombination", "repeat": repeat, "hold_s": hold_s})
        return self._jump_result

    def head_look_reset(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("HeadLookReset", repeat, hold_s)

    def ui_up(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("UI_Up", repeat, hold_s)

    def ui_select(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("UI_Select", repeat, hold_s)

    def ui_down(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("UI_Down", repeat, hold_s)

    def ui_back(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("UI_Back", repeat, hold_s)

    def ui_right(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("UI_Right", repeat, hold_s)

    def ui_left(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("UI_Left", repeat, hold_s)

    def focus_left_panel(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("FocusLeftPanel", repeat, hold_s)

    def cycle_next_panel(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("CycleNextPanel", repeat, hold_s)

    def cycle_previous_panel(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("CyclePreviousPanel", repeat, hold_s)

    def boost(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("BoostButton", repeat, hold_s)

    def galaxy_map_open(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("GalaxyMapOpen", repeat, hold_s)

    def cam_zoom_in(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("CamZoomIn", repeat, hold_s)

    def type_text(self, text: str) -> None:
        self.calls.append({"action": "type_text", "text": text})

    def submit_text(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatch("Enter", repeat, hold_s)


class FakeWatcher:
    def __init__(self, batches: list[list[dict[str, object]]]) -> None:
        self._batches = list(batches)
        self.poll_calls = 0

    def poll(self) -> list[dict[str, object]]:
        self.poll_calls += 1
        if self._batches:
            return self._batches.pop(0)
        return []
