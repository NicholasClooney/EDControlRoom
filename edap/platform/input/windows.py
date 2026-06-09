from __future__ import annotations

from collections.abc import Callable
import ctypes
from time import sleep as _default_sleep

from .base import InputController


KEY_CODES: dict[str, int] = {
    "escape": 0x01,
    "esc": 0x01,
    "1": 0x02,
    "2": 0x03,
    "3": 0x04,
    "4": 0x05,
    "5": 0x06,
    "6": 0x07,
    "7": 0x08,
    "8": 0x09,
    "9": 0x0A,
    "0": 0x0B,
    "-": 0x0C,
    "=": 0x0D,
    "backspace": 0x0E,
    "tab": 0x0F,
    "q": 0x10,
    "w": 0x11,
    "e": 0x12,
    "r": 0x13,
    "t": 0x14,
    "y": 0x15,
    "u": 0x16,
    "i": 0x17,
    "o": 0x18,
    "p": 0x19,
    "[": 0x1A,
    "]": 0x1B,
    "enter": 0x1C,
    "return": 0x1C,
    "left_control": 0x1D,
    "right_control": 0x9D,
    "a": 0x1E,
    "s": 0x1F,
    "d": 0x20,
    "f": 0x21,
    "g": 0x22,
    "h": 0x23,
    "j": 0x24,
    "k": 0x25,
    "l": 0x26,
    ";": 0x27,
    "'": 0x28,
    "`": 0x29,
    "left_shift": 0x2A,
    "\\": 0x2B,
    "z": 0x2C,
    "x": 0x2D,
    "c": 0x2E,
    "v": 0x2F,
    "b": 0x30,
    "n": 0x31,
    "m": 0x32,
    ",": 0x33,
    ".": 0x34,
    "/": 0x35,
    "right_shift": 0x36,
    "left_alt": 0x38,
    "space": 0x39,
    "caps_lock": 0x3A,
    "f1": 0x3B,
    "f2": 0x3C,
    "f3": 0x3D,
    "f4": 0x3E,
    "f5": 0x3F,
    "f6": 0x40,
    "f7": 0x41,
    "f8": 0x42,
    "f9": 0x43,
    "f10": 0x44,
    "num_lock": 0x45,
    "scroll_lock": 0x46,
    "numpad_7": 0x47,
    "numpad_8": 0x48,
    "numpad_9": 0x49,
    "numpad_subtract": 0x4A,
    "numpad_4": 0x4B,
    "numpad_5": 0x4C,
    "numpad_6": 0x4D,
    "numpad_add": 0x4E,
    "numpad_1": 0x4F,
    "numpad_2": 0x50,
    "numpad_3": 0x51,
    "numpad_0": 0x52,
    "numpad_decimal": 0x53,
    "f11": 0x57,
    "f12": 0x58,
    "f13": 0x64,
    "f14": 0x65,
    "f15": 0x66,
    "numpad_enter": 0x9C,
    "numpad_divide": 0xB5,
    "right_alt": 0xB8,
    "home": 0xC7,
    "up": 0xC8,
    "page_up": 0xC9,
    "left": 0xCB,
    "right": 0xCD,
    "end": 0xCF,
    "down": 0xD0,
    "page_down": 0xD1,
    "insert": 0xD2,
    "delete": 0xD3,
    "left_command": 0xDB,
    "right_command": 0xDC,
}


MODIFIER_KEYCODES: dict[str, int] = {
    "shift": KEY_CODES["left_shift"],
    "left_shift": KEY_CODES["left_shift"],
    "right_shift": KEY_CODES["right_shift"],
    "control": KEY_CODES["left_control"],
    "ctrl": KEY_CODES["left_control"],
    "left_control": KEY_CODES["left_control"],
    "right_control": KEY_CODES["right_control"],
    "alt": KEY_CODES["left_alt"],
    "option": KEY_CODES["left_alt"],
    "left_alt": KEY_CODES["left_alt"],
    "left_option": KEY_CODES["left_alt"],
    "right_alt": KEY_CODES["right_alt"],
    "right_option": KEY_CODES["right_alt"],
    "command": KEY_CODES["left_command"],
    "cmd": KEY_CODES["left_command"],
    "left_command": KEY_CODES["left_command"],
    "right_command": KEY_CODES["right_command"],
}


EXTENDED_KEYS = {
    KEY_CODES["right_control"],
    KEY_CODES["right_alt"],
    KEY_CODES["numpad_divide"],
    KEY_CODES["numpad_enter"],
    KEY_CODES["home"],
    KEY_CODES["up"],
    KEY_CODES["page_up"],
    KEY_CODES["left"],
    KEY_CODES["right"],
    KEY_CODES["end"],
    KEY_CODES["down"],
    KEY_CODES["page_down"],
    KEY_CODES["insert"],
    KEY_CODES["delete"],
    KEY_CODES["left_command"],
    KEY_CODES["right_command"],
}


KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1


ULONG_PTR = ctypes.c_size_t


class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class InputUnion(ctypes.Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput),
        ("hi", HardwareInput),
    ]


class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", InputUnion)]


SenderFn = Callable[[int, bool], None]
SleeperFn = Callable[[float], None]


def _is_windows_available() -> bool:
    return hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32")


def _send_input(scan_code: int, is_key_up: bool) -> None:
    if not _is_windows_available():
        raise RuntimeError("Windows SendInput backend is unavailable on this platform.")

    flags = KEYEVENTF_SCANCODE
    if scan_code in EXTENDED_KEYS:
        flags |= KEYEVENTF_EXTENDEDKEY
    if is_key_up:
        flags |= KEYEVENTF_KEYUP

    input_union = InputUnion()
    input_union.ki = KeyBdInput(0, scan_code & 0xFF, flags, 0, 0)
    event = Input(INPUT_KEYBOARD, input_union)
    ctypes.set_last_error(0)
    sent = ctypes.windll.user32.SendInput(1, ctypes.pointer(event), ctypes.sizeof(event))
    if sent != 1:
        error_code = ctypes.get_last_error()
        if error_code:
            raise OSError(
                error_code,
                f"SendInput failed for scan code 0x{scan_code:02X} (WinError {error_code}).",
            )
        raise OSError(f"SendInput failed for scan code 0x{scan_code:02X}.")


def _make_default_sender() -> SenderFn:
    def sender(scan_code: int, down: bool) -> None:
        _send_input(scan_code, not down)

    return sender


class WindowsInputController(InputController):
    def __init__(
        self,
        *,
        sender: SenderFn | None = None,
        sleeper: SleeperFn | None = None,
    ) -> None:
        self._sender = sender if sender is not None else _make_default_sender()
        self._sleeper = sleeper if sleeper is not None else _default_sleep

    def press_key(self, key: str, modifier: str | None = None) -> None:
        keycode, mod_keycode = self._resolve(key, modifier)
        if mod_keycode is not None:
            self._sender(mod_keycode, True)
        self._sender(keycode, True)

    def release_key(self, key: str, modifier: str | None = None) -> None:
        keycode, mod_keycode = self._resolve(key, modifier)
        self._sender(keycode, False)
        if mod_keycode is not None:
            self._sender(mod_keycode, False)

    def tap_key(self, key: str, modifier: str | None = None, hold_s: float = 0.0) -> None:
        keycode, mod_keycode = self._resolve(key, modifier)
        if mod_keycode is not None:
            self._sender(mod_keycode, True)
        self._sender(keycode, True)
        if hold_s > 0:
            self._sleeper(hold_s)
        self._sender(keycode, False)
        if mod_keycode is not None:
            self._sender(mod_keycode, False)

    def type_text(self, text: str, char_delay_s: float = 0.05) -> None:
        special = {"\n": "enter", "\r": "return", "\t": "tab", "\x1b": "esc"}
        shifted = {
            "!": "1",
            "@": "2",
            "#": "3",
            "$": "4",
            "%": "5",
            "^": "6",
            "&": "7",
            "*": "8",
            "(": "9",
            ")": "0",
            "_": "-",
            "+": "=",
            "{": "[",
            "}": "]",
            "|": "\\",
            ":": ";",
            '"': "'",
            "<": ",",
            ">": ".",
            "?": "/",
            "~": "`",
        }
        for char in text:
            if char in special:
                self.tap_key(special[char])
            elif char == " ":
                self.tap_key("space")
            elif char.lower() in KEY_CODES:
                self.tap_key(char.lower(), modifier="left_shift" if char.isupper() else None)
            elif char in shifted:
                self.tap_key(shifted[char], modifier="left_shift")
            else:
                raise ValueError(f"Unsupported character for Windows input: {char!r}")
            if char_delay_s > 0:
                self._sleeper(char_delay_s)

    def _resolve(self, key: str, modifier: str | None) -> tuple[int, int | None]:
        normalized = key.lower()
        if normalized not in KEY_CODES:
            raise ValueError(f"Unsupported key: {key}")

        mod_keycode = None
        if modifier is not None:
            normalized_mod = modifier.lower()
            mod_keycode = MODIFIER_KEYCODES.get(normalized_mod)
            if mod_keycode is None:
                raise ValueError(f"Unsupported modifier: {modifier}")

        return KEY_CODES[normalized], mod_keycode
