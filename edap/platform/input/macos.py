from __future__ import annotations

import subprocess
from time import sleep

from .base import InputController


class MacOSInputController(InputController):
    MODIFIER_KEY_CODES = {
        "command": 55,
        "cmd": 55,
        "shift": 56,
        "left_shift": 56,
        "right_shift": 56,
        "option": 58,
        "alt": 58,
        "left_alt": 58,
        "right_alt": 58,
        "control": 59,
        "ctrl": 59,
        "left_control": 59,
        "right_control": 59,
    }

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
        ",": "comma",
        ".": "period",
        "/": "slash",
        "\\": "backslash",
        ";": "semicolon",
        "'": "quote",
        "-": "minus",
        "=": "equals",
        "[": "left bracket",
        "]": "right bracket",
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
        script = self._build_press_script(key, modifier=modifier)
        self._run_script(script)

    def release_key(self, key: str, modifier: str | None = None) -> None:
        script = self._build_release_script(key, modifier=modifier)
        self._run_script(script)

    def tap_key(self, key: str, modifier: str | None = None, hold_s: float = 0.0) -> None:
        script = self._build_tap_script(key, modifier=modifier, hold_s=hold_s)
        self._run_script(script)

    def _run_script(self, script: str) -> None:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)

    def _build_tap_script(self, key: str, modifier: str | None = None, hold_s: float = 0.0) -> str:
        statements = [
            self._modifier_press_statement(modifier),
            self._key_press_statement(key),
        ]
        if hold_s > 0:
            statements.append(f"delay {hold_s:.3f}")
        statements.extend(
            [
                self._key_release_statement(key),
                self._modifier_release_statement(modifier),
            ]
        )
        return self._wrap_statements(statements)

    def _build_press_script(self, key: str, modifier: str | None = None) -> str:
        return self._wrap_statements(
            [
                self._modifier_press_statement(modifier),
                self._key_press_statement(key),
            ]
        )

    def _build_release_script(self, key: str, modifier: str | None = None) -> str:
        return self._wrap_statements(
            [
                self._key_release_statement(key),
                self._modifier_release_statement(modifier),
            ]
        )

    def _wrap_statements(self, statements: list[str | None]) -> str:
        active_statements = [statement for statement in statements if statement is not None]
        body = "\n  ".join(active_statements)
        return f'tell application "System Events"\n  {body}\nend tell'

    def _key_press_statement(self, key: str) -> str:
        return self._key_statement(key, event="down")

    def _key_release_statement(self, key: str) -> str:
        return self._key_statement(key, event="up")

    def _key_statement(self, key: str, event: str) -> str:
        normalized_key = key.lower()
        if normalized_key in self.SPECIAL_KEYS:
            return f"key {event} key code {self._special_key_code(normalized_key)}"
        escaped_key = key.replace("\\", "\\\\").replace('"', '\\"')
        return f'key {event} "{escaped_key}"'

    def _modifier_press_statement(self, modifier: str | None) -> str | None:
        if modifier is None:
            return None
        return f"key down key code {self._modifier_key_code(modifier)}"

    def _modifier_release_statement(self, modifier: str | None) -> str | None:
        if modifier is None:
            return None
        return f"key up key code {self._modifier_key_code(modifier)}"

    def _build_modifier_clause(self, modifier: str | None) -> str:
        if modifier is None:
            return ""
        normalized = modifier.lower()
        if normalized not in self.MODIFIER_FLAGS:
            raise ValueError(f"Unsupported modifier: {modifier}")
        return f" using {{{self.MODIFIER_FLAGS[normalized]}}}"

    def _modifier_key_code(self, modifier: str) -> int:
        normalized = modifier.lower()
        if normalized not in self.MODIFIER_KEY_CODES:
            raise ValueError(f"Unsupported modifier: {modifier}")
        return self.MODIFIER_KEY_CODES[normalized]

    def _special_key_code(self, key: str) -> int:
        key_codes = {
            "space": 49,
            ",": 43,
            ".": 47,
            "/": 44,
            "\\": 42,
            ";": 41,
            "'": 39,
            "-": 27,
            "=": 24,
            "[": 33,
            "]": 30,
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
