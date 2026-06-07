from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from edap.binding_lookup import build_binding_lookup
from edap.bindings import Binding
from edap.ship_controls import ShipControls


class FakeInputController:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def press_key(self, key: str, modifier: str | None = None) -> None:
        self.calls.append({"method": "press", "key": key, "modifier": modifier})

    def release_key(self, key: str, modifier: str | None = None) -> None:
        self.calls.append({"method": "release", "key": key, "modifier": modifier})

    def tap_key(self, key: str, modifier: str | None = None, hold_s: float = 0.0) -> None:
        self.calls.append(
            {
                "method": "tap",
                "key": key,
                "modifier": modifier,
                "hold_s": hold_s,
            }
        )


class ShipControlsTests(unittest.TestCase):
    def test_set_speed_zero_dispatches_through_binding_lookup(self) -> None:
        lookup = build_binding_lookup(
            bindings={"SetSpeedZero": Binding(key="X")},
            actions=["SetSpeedZero"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller)

        result = controls.set_speed_zero(repeat=2, hold_s=0.05)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.binding.to_dict(), {"key": "x", "modifier": None})
        self.assertEqual(
            input_controller.calls,
            [
                {"method": "tap", "key": "x", "modifier": None, "hold_s": 0.1},
                {"method": "tap", "key": "x", "modifier": None, "hold_s": 0.1},
            ],
        )

    def test_set_speed_zero_reports_missing_binding_without_input(self) -> None:
        lookup = build_binding_lookup(bindings={}, actions=["SetSpeedZero"])
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller)

        result = controls.set_speed_zero()

        self.assertEqual(result.status, "missing")
        self.assertEqual(input_controller.calls, [])

    def test_discrete_action_defaults_to_minimum_hold(self) -> None:
        lookup = build_binding_lookup(
            bindings={"SetSpeedZero": Binding(key="X")},
            actions=["SetSpeedZero"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(
            lookup,
            input_controller,
            minimum_action_hold_s=0.1,
            continuous_action_hold_s=0.2,
        )

        result = controls.set_speed_zero()

        self.assertEqual(result.status, "ok")
        self.assertEqual(input_controller.calls, [{"method": "tap", "key": "x", "modifier": None, "hold_s": 0.1}])

    def test_set_speed_full_dispatches_through_binding_lookup(self) -> None:
        lookup = build_binding_lookup(
            bindings={"SetSpeed100": Binding(key="W")},
            actions=["SetSpeed100"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller)

        result = controls.set_speed_full(hold_s=0.1)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.binding.to_dict(), {"key": "w", "modifier": None})
        self.assertEqual(input_controller.calls, [{"method": "tap", "key": "w", "modifier": None, "hold_s": 0.1}])

    def test_hyper_super_combination_dispatches_through_binding_lookup(self) -> None:
        lookup = build_binding_lookup(
            bindings={"HyperSuperCombination": Binding(key="J", modifier="LeftShift")},
            actions=["HyperSuperCombination"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller)

        result = controls.hyper_super_combination(hold_s=1.0)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.binding.to_dict(), {"key": "j", "modifier": "left_shift"})
        self.assertEqual(
            input_controller.calls,
            [{"method": "tap", "key": "j", "modifier": "left_shift", "hold_s": 1.0}],
        )

    def test_boost_dispatches_through_binding_lookup(self) -> None:
        lookup = build_binding_lookup(
            bindings={"UseBoostJuice": Binding(key="Tab")},
            actions=["UseBoostJuice"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller)

        result = controls.boost()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.binding.to_dict(), {"key": "tab", "modifier": None})
        self.assertEqual(
            input_controller.calls,
            [{"method": "tap", "key": "tab", "modifier": None, "hold_s": 0.1}],
        )

    def test_roll_left_dispatches_through_binding_lookup(self) -> None:
        lookup = build_binding_lookup(
            bindings={"RollLeftButton": Binding(key="A")},
            actions=["RollLeftButton"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller)

        result = controls.roll_left(repeat=2, hold_s=0.05)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.binding.to_dict(), {"key": "a", "modifier": None})
        self.assertEqual(
            input_controller.calls,
            [
                {"method": "tap", "key": "a", "modifier": None, "hold_s": 0.1},
                {"method": "tap", "key": "a", "modifier": None, "hold_s": 0.1},
            ],
        )

    def test_roll_left_uses_default_continuous_hold(self) -> None:
        lookup = build_binding_lookup(
            bindings={"RollLeftButton": Binding(key="A")},
            actions=["RollLeftButton"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller, continuous_action_hold_s=0.2)

        result = controls.roll_left()

        self.assertEqual(result.status, "ok")
        self.assertEqual(input_controller.calls, [{"method": "tap", "key": "a", "modifier": None, "hold_s": 0.2}])

    def test_explicit_hold_is_clamped_to_minimum_hold(self) -> None:
        lookup = build_binding_lookup(
            bindings={"SetSpeedZero": Binding(key="X")},
            actions=["SetSpeedZero"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(
            lookup,
            input_controller,
            minimum_action_hold_s=0.1,
            continuous_action_hold_s=0.2,
        )

        result = controls.set_speed_zero(hold_s=0.01)

        self.assertEqual(result.status, "ok")
        self.assertEqual(input_controller.calls, [{"method": "tap", "key": "x", "modifier": None, "hold_s": 0.1}])

    def test_roll_left_plans_repeat_count_from_total_seconds(self) -> None:
        lookup = build_binding_lookup(
            bindings={"RollLeftButton": Binding(key="A")},
            actions=["RollLeftButton"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller, continuous_action_hold_s=0.2)

        result = controls.roll_left(total_s=0.45)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            input_controller.calls,
            [
                {"method": "tap", "key": "a", "modifier": None, "hold_s": 0.2},
                {"method": "tap", "key": "a", "modifier": None, "hold_s": 0.2},
                {"method": "tap", "key": "a", "modifier": None, "hold_s": 0.2},
            ],
        )

    def test_total_seconds_is_rejected_for_discrete_actions(self) -> None:
        lookup = build_binding_lookup(
            bindings={"SetSpeedZero": Binding(key="X")},
            actions=["SetSpeedZero"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller, continuous_action_hold_s=0.2)

        with self.assertRaisesRegex(ValueError, "total_s is only supported for continuous actions"):
            controls.plan_action("SetSpeedZero", total_s=0.5)

    def test_roll_right_dispatches_through_binding_lookup(self) -> None:
        lookup = build_binding_lookup(
            bindings={"RollRightButton": Binding(key="D", modifier="LeftShift")},
            actions=["RollRightButton"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller)

        result = controls.roll_right()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.binding.to_dict(), {"key": "d", "modifier": "left_shift"})
        self.assertEqual(
            input_controller.calls,
            [{"method": "tap", "key": "d", "modifier": "left_shift", "hold_s": 0.2}],
        )

    def test_ui_select_dispatches_through_binding_lookup(self) -> None:
        lookup = build_binding_lookup(
            bindings={"UI_Select": Binding(key="Space")},
            actions=["UI_Select"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller)

        result = controls.ui_select()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.binding.to_dict(), {"key": "space", "modifier": None})
        self.assertEqual(
            input_controller.calls,
            [{"method": "tap", "key": "space", "modifier": None, "hold_s": 0.1}],
        )

    def test_from_bindings_file_loads_default_ship_control_actions(self) -> None:
        input_controller = FakeInputController()
        bindings_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<Root>
  <SetSpeedZero>
    <Primary Device="Keyboard" Key="Key_X" />
  </SetSpeedZero>
  <SetSpeed100>
    <Primary Device="Keyboard" Key="Key_W" />
  </SetSpeed100>
  <HyperSuperCombination>
    <Primary Device="Keyboard" Key="Key_J">
      <Modifier Device="Keyboard" Key="Key_LeftShift" />
    </Primary>
  </HyperSuperCombination>
  <RollLeftButton>
    <Primary Device="Keyboard" Key="Key_A" />
  </RollLeftButton>
  <RollRightButton>
    <Primary Device="Keyboard" Key="Key_D" />
  </RollRightButton>
  <UI_Select>
    <Primary Device="Keyboard" Key="Space" />
  </UI_Select>
</Root>
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bindings_file = Path(tmpdir) / "Custom.binds"
            bindings_file.write_text(bindings_xml, encoding="utf-8")

            controls = ShipControls.from_bindings_file(bindings_file, input_controller)
            results = [
                controls.set_speed_zero(),
                controls.set_speed_full(),
                controls.hyper_super_combination(hold_s=1.0),
                controls.roll_left(),
                controls.roll_right(),
                controls.ui_select(),
            ]

        self.assertTrue(all(result.status == "ok" for result in results))
        self.assertEqual(
            input_controller.calls,
            [
                {"method": "tap", "key": "x", "modifier": None, "hold_s": 0.1},
                {"method": "tap", "key": "w", "modifier": None, "hold_s": 0.1},
                {"method": "tap", "key": "j", "modifier": "left_shift", "hold_s": 1.0},
                {"method": "tap", "key": "a", "modifier": None, "hold_s": 0.2},
                {"method": "tap", "key": "d", "modifier": None, "hold_s": 0.2},
                {"method": "tap", "key": "space", "modifier": None, "hold_s": 0.1},
            ],
        )

    def test_tap_action_dispatches_arbitrary_action(self) -> None:
        lookup = build_binding_lookup(
            bindings={"RollLeftButton": Binding(key="A")},
            actions=["RollLeftButton"],
        )
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller)

        result = controls.tap_action("RollLeftButton", repeat=3)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.binding.to_dict(), {"key": "a", "modifier": None})
        self.assertEqual(len(input_controller.calls), 3)
