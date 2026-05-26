from __future__ import annotations

import unittest

from edap.actions import ActionDispatchResult, ActionDispatcher
from edap.binding_lookup import build_binding_lookup
from edap.bindings import Binding
from edap.platform.input.macos import MODIFIER_FLAGS, MacOSInputController


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


class ActionDispatcherTests(unittest.TestCase):
    def test_tap_action_dispatches_normalized_binding(self) -> None:
        lookup = build_binding_lookup(
            bindings={"YawLeftButton": Binding(key="A", modifier="LeftShift")},
            actions=["YawLeftButton"],
        )
        input_controller = FakeInputController()
        dispatcher = ActionDispatcher(lookup, input_controller)

        result = dispatcher.tap_action("YawLeftButton", repeat=2, hold_s=0.05)

        self.assertIsInstance(result, ActionDispatchResult)
        self.assertEqual(result.status, "ok")
        self.assertEqual(
            input_controller.calls,
            [
                {"method": "tap", "key": "a", "modifier": "left_shift", "hold_s": 0.05},
                {"method": "tap", "key": "a", "modifier": "left_shift", "hold_s": 0.05},
            ],
        )

    def test_tap_action_reports_missing_without_dispatching_input(self) -> None:
        lookup = build_binding_lookup(bindings={}, actions=["UI_Back"])
        input_controller = FakeInputController()
        dispatcher = ActionDispatcher(lookup, input_controller)

        result = dispatcher.tap_action("UI_Back")

        self.assertEqual(result.status, "missing")
        self.assertEqual(input_controller.calls, [])

    def test_tap_action_rejects_invalid_repeat_and_hold(self) -> None:
        lookup = build_binding_lookup(
            bindings={"UI_Back": Binding(key="Backspace")},
            actions=["UI_Back"],
        )
        dispatcher = ActionDispatcher(lookup, FakeInputController())

        with self.assertRaisesRegex(ValueError, "repeat must be at least 1"):
            dispatcher.tap_action("UI_Back", repeat=0)
        with self.assertRaisesRegex(ValueError, "hold_s must be non-negative"):
            dispatcher.tap_action("UI_Back", hold_s=-0.1)

    def test_macos_input_accepts_left_right_modifier_aliases(self) -> None:
        events: list[tuple] = []
        input_controller = MacOSInputController(
            poster=lambda keycode, down, flags, unicode_char: events.append(
                ("down" if down else "up", flags)
            ),
            sleeper=lambda _duration: None,
        )

        input_controller.tap_key("a", modifier="left_shift")
        input_controller.tap_key("a", modifier="right_control")

        shift_flags = MODIFIER_FLAGS["shift"]
        control_flags = MODIFIER_FLAGS["control"]
        self.assertEqual(
            events,
            [
                ("down", shift_flags),
                ("up", shift_flags),
                ("down", control_flags),
                ("up", control_flags),
            ],
        )
