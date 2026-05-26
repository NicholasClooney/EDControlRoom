"""
Scratch prototype that sends a single keyboard event via Quartz CGEvent
instead of osascript, so we can A/B test whether the lower-level path
fixes the cases the current osascript backend can't:

- `.` (Key_Period) reaches chat but does not trigger PitchDownButton in flight
- modifier-combo ship controls like Ctrl+...

Install once:
    python3 -m pip install pyobjc-framework-Quartz

Usage:
    python3 scratch_cgevent.py <key> [--hold 0.4] [--modifier ctrl] \\
        [--unicode|--no-unicode] [--delay 3.0]
    python3 scratch_cgevent.py --sequence "x; a hold=0.4 delay=1; . hold=0.4 delay=1"

Examples:
    python3 scratch_cgevent.py a --hold 0.5
    python3 scratch_cgevent.py . --hold 0.5
    python3 scratch_cgevent.py . --hold 0.5 --no-unicode
    python3 scratch_cgevent.py x --modifier ctrl --hold 0.2

Sequence per-step fields: hold=<seconds> delay=<seconds> modifier=<name>

The `--unicode` flag (default on) attaches a Unicode character payload to
the event, similar to osascript `key down "x"`. `--no-unicode` sends the
raw virtual-key-code event only, similar to osascript `key down key code N`.
Comparing the two for `.` directly tests whether the missing payload is
why ED's `Key_Period` binding never matched.
"""
from __future__ import annotations

import argparse
import time

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


KEY_CODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23,
    "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
    "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35,
    "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42,
    ",": 43, "/": 44, "n": 45, "m": 46, ".": 47,
    "return": 36, "enter": 36, "tab": 48, "space": 49,
    "`": 50, "delete": 51, "escape": 53,
    "left": 123, "right": 124, "down": 125, "up": 126,
}

MODIFIER_FLAGS = {
    "shift": kCGEventFlagMaskShift,
    "control": kCGEventFlagMaskControl,
    "ctrl": kCGEventFlagMaskControl,
    "option": kCGEventFlagMaskAlternate,
    "alt": kCGEventFlagMaskAlternate,
    "command": kCGEventFlagMaskCommand,
    "cmd": kCGEventFlagMaskCommand,
}


def post_key(key: str, hold_s: float, modifier: str | None, with_unicode: bool) -> None:
    normalized = key.lower()
    if normalized not in KEY_CODES:
        raise SystemExit(f"unknown key: {key!r}")
    keycode = KEY_CODES[normalized]

    flags = 0
    if modifier is not None:
        normalized_mod = modifier.lower()
        if normalized_mod not in MODIFIER_FLAGS:
            raise SystemExit(f"unknown modifier: {modifier!r}")
        flags = MODIFIER_FLAGS[normalized_mod]

    source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)

    down = CGEventCreateKeyboardEvent(source, keycode, True)
    up = CGEventCreateKeyboardEvent(source, keycode, False)

    if flags:
        CGEventSetFlags(down, flags)
        CGEventSetFlags(up, flags)

    if with_unicode and len(key) == 1:
        CGEventKeyboardSetUnicodeString(down, 1, key)
        CGEventKeyboardSetUnicodeString(up, 1, key)

    CGEventPost(kCGHIDEventTap, down)
    time.sleep(hold_s)
    CGEventPost(kCGHIDEventTap, up)


def _parse_sequence(raw: str) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    for raw_step in raw.split(";"):
        step_text = raw_step.strip()
        if not step_text:
            continue
        parts = step_text.split()
        step: dict[str, object] = {"key": parts[0], "hold": None, "delay": None, "modifier": None}
        for token in parts[1:]:
            if "=" not in token:
                raise SystemExit(f"invalid sequence token: {token}")
            field, value = token.split("=", 1)
            if field == "hold":
                step["hold"] = float(value)
            elif field == "delay":
                step["delay"] = float(value)
            elif field == "modifier":
                step["modifier"] = value
            else:
                raise SystemExit(f"unsupported sequence field: {field}")
        steps.append(step)
    if not steps:
        raise SystemExit("sequence must contain at least one step")
    return steps


def main() -> None:
    parser = argparse.ArgumentParser(description="CGEvent keyboard input prototype")
    parser.add_argument("key", nargs="?", help="single key character or special name (omit when using --sequence)")
    parser.add_argument("--hold", type=float, default=0.4, help="hold duration in seconds")
    parser.add_argument("--modifier", default=None, help="optional modifier: shift, ctrl, alt, cmd")
    parser.add_argument("--delay", type=float, default=3.0, help="seconds to wait before sending")
    parser.add_argument(
        "--sequence",
        default=None,
        help="semicolon-separated steps, e.g. 'x; a hold=0.4 delay=1; . hold=0.4 delay=1'",
    )
    parser.add_argument(
        "--unicode",
        dest="with_unicode",
        action="store_true",
        default=True,
        help="attach a Unicode character payload to events (default)",
    )
    parser.add_argument(
        "--no-unicode",
        dest="with_unicode",
        action="store_false",
        help="send raw virtual-key-code events with no character payload",
    )
    args = parser.parse_args()

    if args.sequence is None and args.key is None:
        parser.error("either <key> or --sequence is required")

    if args.delay > 0:
        target = args.sequence if args.sequence else args.key
        print(f"starting in {args.delay:.1f}s — focus the game window ({target!r})")
        time.sleep(args.delay)

    if args.sequence is not None:
        steps = _parse_sequence(args.sequence)
        for index, step in enumerate(steps, start=1):
            if step["delay"] is not None and step["delay"] > 0:
                time.sleep(step["delay"])
            key = step["key"]
            hold_s = step["hold"] if step["hold"] is not None else args.hold
            modifier = step["modifier"] if step["modifier"] is not None else args.modifier
            print(f"step {index}/{len(steps)}: {key!r} hold={hold_s:.2f}s modifier={modifier}")
            post_key(key, hold_s, modifier, args.with_unicode)
    else:
        post_key(args.key, args.hold, args.modifier, args.with_unicode)

    print("sent")


if __name__ == "__main__":
    main()
