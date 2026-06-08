from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from time import sleep

from edap.actions import ActionDispatchResult, ActionDispatcher
from edap.binding_lookup import BindingLookup, load_binding_lookup
from edap.platform.input.base import InputController


DEFAULT_SHIP_CONTROL_ACTIONS = [
    "SetSpeedZero",
    "SetSpeed100",
    "HyperSuperCombination",
    "UseBoostJuice",
    "FocusLeftPanel",
    "UI_Back",
    "UIFocus",
    "UI_Left",
    "UI_Right",
    "UI_Up",
    "UI_Down",
    "CycleNextPanel",
    "CyclePreviousPanel",
    "HeadLookReset",
    "RollLeftButton",
    "RollRightButton",
    "UI_Select",
    "GalaxyMapOpen",
    "CamZoomIn",
]

CONTINUOUS_ACTIONS = {
    "RollLeftButton",
    "RollRightButton",
    "PitchUpButton",
    "PitchDownButton",
    "YawLeftButton",
    "YawRightButton",
}


@dataclass(frozen=True)
class ActionPlan:
    action: str
    repeat: int
    hold_s: float
    total_s: float | None = None

    @property
    def is_continuous(self) -> bool:
        return self.action in CONTINUOUS_ACTIONS


class ShipControls:
    """Narrow runtime-facing ship control wrapper for binding-driven actions."""

    def __init__(
        self,
        dispatcher: ActionDispatcher,
        *,
        minimum_action_hold_s: float = 0.1,
        continuous_action_hold_s: float = 0.2,
    ) -> None:
        self._dispatcher = dispatcher
        self._minimum_action_hold_s = minimum_action_hold_s
        self._continuous_action_hold_s = continuous_action_hold_s

    @classmethod
    def from_binding_lookup(
        cls,
        binding_lookup: BindingLookup,
        input_controller: InputController,
        *,
        minimum_action_hold_s: float = 0.1,
        continuous_action_hold_s: float = 0.2,
    ) -> ShipControls:
        return cls(
            ActionDispatcher(
                binding_lookup,
                input_controller,
                repeat_delay_s=minimum_action_hold_s,
                sleeper=sleep,
            ),
            minimum_action_hold_s=minimum_action_hold_s,
            continuous_action_hold_s=continuous_action_hold_s,
        )

    @classmethod
    def from_bindings_file(
        cls,
        bindings_file: Path,
        input_controller: InputController,
        actions: list[str] | None = None,
        *,
        minimum_action_hold_s: float = 0.1,
        continuous_action_hold_s: float = 0.2,
    ) -> ShipControls:
        binding_lookup = load_binding_lookup(bindings_file, actions=actions or DEFAULT_SHIP_CONTROL_ACTIONS)
        return cls.from_binding_lookup(
            binding_lookup,
            input_controller,
            minimum_action_hold_s=minimum_action_hold_s,
            continuous_action_hold_s=continuous_action_hold_s,
        )

    def plan_action(
        self,
        action: str,
        *,
        repeat: int = 1,
        hold_s: float | None = None,
        total_s: float | None = None,
    ) -> ActionPlan:
        if repeat < 1:
            raise ValueError("repeat must be at least 1")
        if hold_s is not None and hold_s < 0:
            raise ValueError("hold_s must be non-negative")
        if total_s is not None and total_s < 0:
            raise ValueError("total_s must be non-negative")

        is_continuous = action in CONTINUOUS_ACTIONS
        default_hold_s = self._continuous_action_hold_s if is_continuous else self._minimum_action_hold_s
        requested_hold_s = hold_s if hold_s is not None else default_hold_s
        planned_hold_s = max(self._minimum_action_hold_s, requested_hold_s)

        if total_s is not None:
            if not is_continuous:
                raise ValueError("total_s is only supported for continuous actions")
            if planned_hold_s <= 0:
                raise ValueError("continuous actions require a positive hold_s")
            repeat = max(1, int(math.ceil(total_s / planned_hold_s)))

        return ActionPlan(
            action=action,
            repeat=repeat,
            hold_s=planned_hold_s,
            total_s=total_s,
        )

    def tap_action(self, action: str, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        if repeat < 1:
            raise ValueError("repeat must be at least 1")
        if hold_s < 0:
            raise ValueError("hold_s must be non-negative")
        return self._dispatcher.tap_action(action, repeat=repeat, hold_s=hold_s)

    def dispatch_action(
        self,
        action: str,
        *,
        repeat: int = 1,
        hold_s: float | None = None,
        total_s: float | None = None,
    ) -> ActionDispatchResult:
        plan = self.plan_action(action, repeat=repeat, hold_s=hold_s, total_s=total_s)
        return self.tap_action(plan.action, repeat=plan.repeat, hold_s=plan.hold_s)

    def set_speed_zero(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("SetSpeedZero", repeat=repeat, hold_s=hold_s)

    def set_speed_full(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("SetSpeed100", repeat=repeat, hold_s=hold_s)

    def roll_left(
        self,
        repeat: int = 1,
        hold_s: float | None = None,
        total_s: float | None = None,
    ) -> ActionDispatchResult:
        return self.dispatch_action("RollLeftButton", repeat=repeat, hold_s=hold_s, total_s=total_s)

    def roll_right(
        self,
        repeat: int = 1,
        hold_s: float | None = None,
        total_s: float | None = None,
    ) -> ActionDispatchResult:
        return self.dispatch_action("RollRightButton", repeat=repeat, hold_s=hold_s, total_s=total_s)

    def ui_select(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("UI_Select", repeat=repeat, hold_s=hold_s)

    def focus_left_panel(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("FocusLeftPanel", repeat=repeat, hold_s=hold_s)

    def ui_back(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("UI_Back", repeat=repeat, hold_s=hold_s)

    def ui_focus(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("UIFocus", repeat=repeat, hold_s=hold_s)

    def ui_left(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("UI_Left", repeat=repeat, hold_s=hold_s)

    def ui_right(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("UI_Right", repeat=repeat, hold_s=hold_s)

    def ui_up(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("UI_Up", repeat=repeat, hold_s=hold_s)

    def ui_down(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("UI_Down", repeat=repeat, hold_s=hold_s)

    def cycle_next_panel(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("CycleNextPanel", repeat=repeat, hold_s=hold_s)

    def cycle_previous_panel(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("CyclePreviousPanel", repeat=repeat, hold_s=hold_s)

    def head_look_reset(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("HeadLookReset", repeat=repeat, hold_s=hold_s)

    def boost(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("UseBoostJuice", repeat=repeat, hold_s=hold_s)

    def hyper_super_combination(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("HyperSuperCombination", repeat=repeat, hold_s=hold_s)

    def galaxy_map_open(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("GalaxyMapOpen", repeat=repeat, hold_s=hold_s)

    def cam_zoom_in(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
        return self.dispatch_action("CamZoomIn", repeat=repeat, hold_s=hold_s)

    def type_text(self, text: str, char_delay_s: float = 0.05) -> None:
        self._dispatcher.type_text(text, char_delay_s=char_delay_s)

    def submit_text(self, repeat: int = 1, hold_s: float = 0.2) -> ActionDispatchResult:
        return self._dispatcher.tap_key("enter", repeat=repeat, hold_s=hold_s)

    def tap_key(
        self,
        key: str,
        *,
        modifier: str | None = None,
        repeat: int = 1,
        hold_s: float | None = None,
    ) -> ActionDispatchResult:
        plan = self.plan_action(f"raw:{key}", repeat=repeat, hold_s=hold_s)
        return self._dispatcher.tap_key(key, modifier=modifier, repeat=plan.repeat, hold_s=plan.hold_s)
