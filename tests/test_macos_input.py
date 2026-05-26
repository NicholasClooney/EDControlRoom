from __future__ import annotations

import unittest

from edap.platform.input.macos import KEY_CODES, MODIFIER_FLAGS, MacOSInputController


class FakeBackend:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def post(self, keycode: int, down: bool, flags: int, unicode_char: str | None) -> None:
        self.events.append(("down" if down else "up", keycode, flags, unicode_char))

    def sleep(self, duration: float) -> None:
        self.events.append(("sleep", duration))


def _build() -> tuple[MacOSInputController, FakeBackend]:
    backend = FakeBackend()
    return (
        MacOSInputController(poster=backend.post, sleeper=backend.sleep),
        backend,
    )


class MacOSInputControllerTests(unittest.TestCase):
    def test_tap_letter_with_hold(self) -> None:
        controller, backend = _build()

        controller.tap_key("a", hold_s=0.1)

        self.assertEqual(
            backend.events,
            [
                ("down", KEY_CODES["a"], 0, "a"),
                ("sleep", 0.1),
                ("up", KEY_CODES["a"], 0, "a"),
            ],
        )

    def test_tap_with_zero_hold_skips_sleep(self) -> None:
        controller, backend = _build()

        controller.tap_key("x")

        self.assertEqual(
            backend.events,
            [
                ("down", KEY_CODES["x"], 0, "x"),
                ("up", KEY_CODES["x"], 0, "x"),
            ],
        )

    def test_tap_with_control_modifier(self) -> None:
        controller, backend = _build()

        controller.tap_key("x", modifier="control", hold_s=0.05)

        flags = MODIFIER_FLAGS["control"]
        self.assertNotEqual(flags, 0)
        self.assertEqual(
            backend.events,
            [
                ("down", KEY_CODES["x"], flags, "x"),
                ("sleep", 0.05),
                ("up", KEY_CODES["x"], flags, "x"),
            ],
        )

    def test_punctuation_uses_correct_keycodes(self) -> None:
        controller, backend = _build()

        for character in (",", ".", "[", "]"):
            backend.events.clear()
            controller.tap_key(character, hold_s=0.2)

            self.assertEqual(
                backend.events,
                [
                    ("down", KEY_CODES[character], 0, character),
                    ("sleep", 0.2),
                    ("up", KEY_CODES[character], 0, character),
                ],
                msg=f"unexpected events for {character!r}",
            )

    def test_press_and_release_are_split(self) -> None:
        controller, backend = _build()

        controller.press_key("left", modifier="right_control")
        controller.release_key("left", modifier="right_control")

        flags = MODIFIER_FLAGS["right_control"]
        self.assertEqual(
            backend.events,
            [
                ("down", KEY_CODES["left"], flags, None),
                ("up", KEY_CODES["left"], flags, None),
            ],
        )

    def test_multi_char_key_sends_no_unicode_payload(self) -> None:
        controller, backend = _build()

        controller.tap_key("left_shift")

        self.assertEqual(
            backend.events,
            [
                ("down", KEY_CODES["left_shift"], 0, None),
                ("up", KEY_CODES["left_shift"], 0, None),
            ],
        )

    def test_unsupported_key_raises(self) -> None:
        controller, _ = _build()

        with self.assertRaises(ValueError):
            controller.tap_key("not_a_real_key")

    def test_unsupported_modifier_raises(self) -> None:
        controller, _ = _build()

        with self.assertRaises(ValueError):
            controller.tap_key("a", modifier="weird")
