from __future__ import annotations

import subprocess
from time import sleep

from .base import InputController


class MacOSInputController(InputController):
    MODIFIER_FLAGS = {
        "command": "command down",
        "cmd": "command down",
        "shift": "shift down",
        "left_shift": "shift down",
        "right_shift": "shift down",
        "option": "option down",
        "alt": "option down",
        "left_alt": "option down",
        "right_alt": "option down",
        "control": "control down",
        "ctrl": "control down",
        "left_control": "control down",
        "right_control": "control down",
    }

    SPECIAL_KEYS = {
        "space": "space",
        "return": "return",
        "enter": "return",
        "tab": "tab",
        "escape": "escape",
        "esc": "escape",
        "delete": "delete",
        "up": "up arrow",
        "down": "down arrow",
        "left": "left arrow",
        "right": "right arrow",
    }

    def press_key(self, key: str, modifier: str | None = None) -> None:
        self.tap_key(key, modifier=modifier, hold_s=0.0)

    def release_key(self, key: str, modifier: str | None = None) -> None:
        return None

    def tap_key(self, key: str, modifier: str | None = None, hold_s: float = 0.0) -> None:
        script = self._build_script(key, modifier=modifier)
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        if hold_s > 0:
            sleep(hold_s)

    def _build_script(self, key: str, modifier: str | None = None) -> str:
        normalized_key = key.lower()
        modifiers = self._build_modifier_clause(modifier)
        if normalized_key in self.SPECIAL_KEYS:
            key_expr = self.SPECIAL_KEYS[normalized_key]
            return (
                'tell application "System Events" to key code '
                f"{self._special_key_code(normalized_key)}{modifiers}"
            )
        escaped_key = key.replace("\\", "\\\\").replace('"', '\\"')
        return f'tell application "System Events" to keystroke "{escaped_key}"{modifiers}'

    def _build_modifier_clause(self, modifier: str | None) -> str:
        if modifier is None:
            return ""
        normalized = modifier.lower()
        if normalized not in self.MODIFIER_FLAGS:
            raise ValueError(f"Unsupported modifier: {modifier}")
        return f" using {{{self.MODIFIER_FLAGS[normalized]}}}"

    def _special_key_code(self, key: str) -> int:
        key_codes = {
            "space": 49,
            "return": 36,
            "enter": 76,
            "tab": 48,
            "escape": 53,
            "esc": 53,
            "delete": 51,
            "up": 126,
            "down": 125,
            "left": 123,
            "right": 124,
        }
        return key_codes[key]
