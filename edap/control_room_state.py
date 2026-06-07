from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


@dataclass
class CommandHistoryEntry:
    raw: str
    command: str
    params: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class ControlRoomState:
    haul_defaults: dict[str, str] = field(default_factory=dict)
    dest_defaults: dict[str, Any] = field(default_factory=dict)
    history: list[CommandHistoryEntry] = field(default_factory=list)


def load_control_room_state(path: Path) -> ControlRoomState:
    if not path.exists():
        return ControlRoomState()

    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    if not isinstance(raw, dict):
        return ControlRoomState()

    haul_defaults = raw.get("haul_defaults", {})
    if not isinstance(haul_defaults, dict):
        haul_defaults = {}

    dest_defaults = raw.get("dest_defaults", {})
    if not isinstance(dest_defaults, dict):
        dest_defaults = {}

    raw_history = raw.get("history", [])
    history: list[CommandHistoryEntry] = []
    if isinstance(raw_history, list):
        for item in raw_history:
            if not isinstance(item, dict):
                continue
            raw_command = item.get("raw", "")
            command = item.get("command", "")
            params = item.get("params", {})
            timestamp = item.get("timestamp", "")
            if not isinstance(raw_command, str) or not isinstance(command, str):
                continue
            if not isinstance(params, dict):
                params = {}
            if not isinstance(timestamp, str):
                timestamp = ""
            history.append(
                CommandHistoryEntry(
                    raw=raw_command,
                    command=command,
                    params=params,
                    timestamp=timestamp,
                )
            )

    return ControlRoomState(
        haul_defaults={str(key): str(value) for key, value in haul_defaults.items()},
        dest_defaults=dest_defaults,
        history=history,
    )


def save_control_room_state(path: Path, state: ControlRoomState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "haul_defaults": state.haul_defaults,
        "dest_defaults": state.dest_defaults,
        "history": [
            {
                "raw": entry.raw,
                "command": entry.command,
                "params": entry.params,
                "timestamp": entry.timestamp,
            }
            for entry in state.history
        ],
    }

    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)

    temp_path.replace(path)
