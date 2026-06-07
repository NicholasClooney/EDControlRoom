from __future__ import annotations

import inspect
import unittest

from edap.progress_controls import ProgressShipControls
from edap.ship_controls import DEFAULT_SHIP_CONTROL_ACTIONS, ShipControls

# Every action string dispatched by ShipControls methods. Update this set when
# a new method is added to ShipControls so the test fails loudly if the action
# is also missing from DEFAULT_SHIP_CONTROL_ACTIONS.
_EXPECTED_DEFAULT_ACTIONS = {
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
}


# Infrastructure methods on ShipControls that ProgressShipControls intentionally
# does not forward -- they are construction or internal dispatch helpers, not
# action-dispatching methods used by routines.
_SHIP_CONTROLS_INTERNAL = {
    "plan_action",
    "tap_action",
    "dispatch_action",
    "from_binding_lookup",
    "from_bindings_file",
}


def _action_methods(cls: type) -> set[str]:
    return {
        name
        for name, _ in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_") and name not in _SHIP_CONTROLS_INTERNAL
    }


class TestProgressShipControlsCompleteness(unittest.TestCase):
    def test_forwards_all_ship_controls_methods(self) -> None:
        ship = _action_methods(ShipControls)
        progress = _action_methods(ProgressShipControls)
        missing = ship - progress
        self.assertEqual(
            missing,
            set(),
            f"ProgressShipControls is missing methods present on ShipControls: {missing}",
        )


class TestDefaultShipControlActions(unittest.TestCase):
    def test_contains_all_expected_actions(self) -> None:
        actual = set(DEFAULT_SHIP_CONTROL_ACTIONS)
        missing = _EXPECTED_DEFAULT_ACTIONS - actual
        self.assertEqual(
            missing,
            set(),
            f"DEFAULT_SHIP_CONTROL_ACTIONS is missing actions: {missing}",
        )

    def test_no_unexpected_actions(self) -> None:
        actual = set(DEFAULT_SHIP_CONTROL_ACTIONS)
        extra = actual - _EXPECTED_DEFAULT_ACTIONS
        self.assertEqual(
            extra,
            set(),
            f"DEFAULT_SHIP_CONTROL_ACTIONS has undocumented actions (update _EXPECTED_DEFAULT_ACTIONS): {extra}",
        )
