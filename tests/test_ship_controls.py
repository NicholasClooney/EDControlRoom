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
                {"method": "tap", "key": "x", "modifier": None, "hold_s": 0.05},
                {"method": "tap", "key": "x", "modifier": None, "hold_s": 0.05},
            ],
        )

    def test_set_speed_zero_reports_missing_binding_without_input(self) -> None:
        lookup = build_binding_lookup(bindings={}, actions=["SetSpeedZero"])
        input_controller = FakeInputController()
        controls = ShipControls.from_binding_lookup(lookup, input_controller)

        result = controls.set_speed_zero()

        self.assertEqual(result.status, "missing")
        self.assertEqual(input_controller.calls, [])

    def test_from_bindings_file_loads_set_speed_zero_binding(self) -> None:
        input_controller = FakeInputController()
        bindings_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<Root>
  <SetSpeedZero>
    <Primary Device="Keyboard" Key="Key_X" />
  </SetSpeedZero>
</Root>
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bindings_file = Path(tmpdir) / "Custom.binds"
            bindings_file.write_text(bindings_xml, encoding="utf-8")

            controls = ShipControls.from_bindings_file(bindings_file, input_controller)
            result = controls.set_speed_zero()

        self.assertEqual(result.status, "ok")
        self.assertEqual(input_controller.calls, [{"method": "tap", "key": "x", "modifier": None, "hold_s": 0.0}])

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
