"""
ED AutoPilot Control Room

Thin launcher for the control-room Textual app.

Usage:
    uv run python3 control_room.py
"""

from edap.control_room.app import (
    ControlRoomApp,
    _ALL_ROUTINE_ACTIONS,
    _build_log_text,
    _cargo_summary_lines,
    _DEFAULT_COMMAND_PLACEHOLDER,
    _fmt_cr,
    _fuel_bar,
    _fmt_duration,
    _hhmmss,
    _is_recent,
    _loc,
    _read_cargo_inventory,
    main,
)


if __name__ == "__main__":
    main()
