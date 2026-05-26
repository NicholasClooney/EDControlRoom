from __future__ import annotations

import unittest

from edap.platform.input.macos import MacOSInputController


class MacOSInputControllerTests(unittest.TestCase):
    def test_tap_script_uses_real_key_down_and_key_up(self) -> None:
        input_controller = MacOSInputController()

        script = input_controller._build_tap_script("a", hold_s=0.1)

        self.assertEqual(
            script,
            'tell application "System Events"\n'
            '  key down "a"\n'
            "  delay 0.100\n"
            '  key up "a"\n'
            "end tell",
        )

    def test_tap_script_wraps_modifier_around_key(self) -> None:
        input_controller = MacOSInputController()

        script = input_controller._build_tap_script("x", modifier="left_shift", hold_s=0.05)

        self.assertEqual(
            script,
            'tell application "System Events"\n'
            "  key down key code 56\n"
            '  key down "x"\n'
            "  delay 0.050\n"
            '  key up "x"\n'
            "  key up key code 56\n"
            "end tell",
        )

    def test_press_and_release_scripts_are_split(self) -> None:
        input_controller = MacOSInputController()

        press_script = input_controller._build_press_script("left", modifier="right_control")
        release_script = input_controller._build_release_script("left", modifier="right_control")

        self.assertEqual(
            press_script,
            'tell application "System Events"\n'
            "  key down key code 59\n"
            "  key down key code 123\n"
            "end tell",
        )
        self.assertEqual(
            release_script,
            'tell application "System Events"\n'
            "  key up key code 123\n"
            "  key up key code 59\n"
            "end tell",
        )

    def test_punctuation_keys_use_key_codes(self) -> None:
        input_controller = MacOSInputController()

        script = input_controller._build_tap_script(".", hold_s=0.2)

        self.assertEqual(
            script,
            'tell application "System Events"\n'
            "  key down key code 47\n"
            "  delay 0.200\n"
            "  key up key code 47\n"
            "end tell",
        )
