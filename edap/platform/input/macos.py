from __future__ import annotations

from collections.abc import Callable
from time import sleep as _default_sleep

from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventKeyboardSetUnicodeString,
    CGEventPost,
    CGEventSetFlags,
    CGEventSourceCreate,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskShift,
    kCGEventSourceStateHIDSystemState,
    kCGHIDEventTap,
)

from .base import InputController


KEY_CODES: dict[str, int] = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23,
    "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
    "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35,
    "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42,
    ",": 43, "/": 44, "n": 45, "m": 46, ".": 47,
    "enter": 36,
    "return": 36,
    "tab": 48,
    "space": 49,
    "`": 50,
    "backspace": 51,
    "escape": 53,
    "esc": 53,
    "right_command": 54,
    "left_command": 55,
    "left_shift": 56,
    "right_shift": 60,
    "left_option": 58,
    "right_option": 61,
    "left_alt": 58,
    "right_alt": 61,
    "left_control": 59,
    "right_control": 62,
    "numpad_0": 82, "numpad_1": 83, "numpad_2": 84, "numpad_3": 85,
    "numpad_4": 86, "numpad_5": 87, "numpad_6": 88, "numpad_7": 89,
    "numpad_8": 91, "numpad_9": 92,
    "home": 115,
    "page_up": 116,
    "delete": 117,
    "end": 119,
    "page_down": 121,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "f13": 105, "f14": 107, "f15": 113, "f16": 106, "f17": 64,
    "f18": 79, "f19": 80, "f20": 90,
}


MODIFIER_FLAGS: dict[str, int] = {
    "shift": kCGEventFlagMaskShift,
    "left_shift": kCGEventFlagMaskShift,
    "right_shift": kCGEventFlagMaskShift,
    "control": kCGEventFlagMaskControl,
    "ctrl": kCGEventFlagMaskControl,
    "left_control": kCGEventFlagMaskControl,
    "right_control": kCGEventFlagMaskControl,
    "option": kCGEventFlagMaskAlternate,
    "alt": kCGEventFlagMaskAlternate,
    "left_option": kCGEventFlagMaskAlternate,
    "right_option": kCGEventFlagMaskAlternate,
    "left_alt": kCGEventFlagMaskAlternate,
    "right_alt": kCGEventFlagMaskAlternate,
    "command": kCGEventFlagMaskCommand,
    "cmd": kCGEventFlagMaskCommand,
    "left_command": kCGEventFlagMaskCommand,
    "right_command": kCGEventFlagMaskCommand,
}


PosterFn = Callable[[int, bool, int, "str | None"], None]
SleeperFn = Callable[[float], None]


def _make_default_poster() -> PosterFn:
    source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)

    def poster(keycode: int, down: bool, flags: int, unicode_char: str | None) -> None:
        event = CGEventCreateKeyboardEvent(source, keycode, down)
        if flags:
            CGEventSetFlags(event, flags)
        if unicode_char is not None:
            CGEventKeyboardSetUnicodeString(event, 1, unicode_char)
        CGEventPost(kCGHIDEventTap, event)

    return poster


class MacOSInputController(InputController):
    def __init__(
        self,
        *,
        poster: PosterFn | None = None,
        sleeper: SleeperFn | None = None,
    ) -> None:
        self._poster = poster if poster is not None else _make_default_poster()
        self._sleeper = sleeper if sleeper is not None else _default_sleep

    def press_key(self, key: str, modifier: str | None = None) -> None:
        keycode, flags, unicode_char = self._resolve(key, modifier)
        self._poster(keycode, True, flags, unicode_char)

    def release_key(self, key: str, modifier: str | None = None) -> None:
        keycode, flags, unicode_char = self._resolve(key, modifier)
        self._poster(keycode, False, flags, unicode_char)

    def tap_key(self, key: str, modifier: str | None = None, hold_s: float = 0.0) -> None:
        keycode, flags, unicode_char = self._resolve(key, modifier)
        self._poster(keycode, True, flags, unicode_char)
        if hold_s > 0:
            self._sleeper(hold_s)
        self._poster(keycode, False, flags, unicode_char)

    def type_text(self, text: str, char_delay_s: float = 0.05) -> None:
        _SPECIAL: dict[str, str] = {"\n": "enter", "\r": "return", "\t": "tab", "\x1b": "esc"}
        for char in text:
            if char in _SPECIAL:
                self.tap_key(_SPECIAL[char])
            else:
                self._poster(0, True, 0, char)
                self._poster(0, False, 0, char)
            if char_delay_s > 0:
                self._sleeper(char_delay_s)

    def _resolve(self, key: str, modifier: str | None) -> tuple[int, int, str | None]:
        normalized = key.lower()
        if normalized not in KEY_CODES:
            raise ValueError(f"Unsupported key: {key}")
        keycode = KEY_CODES[normalized]

        flags = 0
        if modifier is not None:
            normalized_mod = modifier.lower()
            if normalized_mod not in MODIFIER_FLAGS:
                raise ValueError(f"Unsupported modifier: {modifier}")
            flags = MODIFIER_FLAGS[normalized_mod]

        unicode_char = key if len(key) == 1 else None
        return keycode, flags, unicode_char
