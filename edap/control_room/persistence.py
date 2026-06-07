from __future__ import annotations

from pathlib import Path
from typing import Protocol

from rich.markup import escape

from edap.config import AppConfig
from edap.control_room_state import (
    CommandHistoryEntry,
    ControlRoomState,
    load_control_room_state,
    save_control_room_state,
)


class PersistenceHost(Protocol):
    _config: AppConfig
    _saved_state: ControlRoomState
    _state_path: Path
    _history: list[str]
    _history_pos: int
    _history_draft: str

    def _log(self, msg: str) -> None: ...


def load_saved_state(app: PersistenceHost) -> None:
    try:
        app._saved_state = load_control_room_state(app._state_path)
    except Exception as exc:
        app._saved_state = ControlRoomState()
        app._log(
            f"[yellow]Failed to load control-room state "
            f"from {escape(str(app._state_path))}: {escape(str(exc))}[/]"
        )
    app._history = [entry.raw for entry in app._saved_state.history if entry.raw]
    app._history_pos = len(app._history)


def save_saved_state(app: PersistenceHost) -> None:
    try:
        save_control_room_state(app._state_path, app._saved_state)
    except Exception as exc:
        app._log(
            f"[yellow]Failed to save control-room state "
            f"to {escape(str(app._state_path))}: {escape(str(exc))}[/]"
        )


def record_history_entry(app: PersistenceHost, entry: CommandHistoryEntry) -> None:
    if (
        app._saved_state.history
        and app._saved_state.history[-1].raw == entry.raw
        and app._saved_state.history[-1].params == entry.params
    ):
        app._saved_state.history[-1] = entry
    else:
        app._saved_state.history.append(entry)

    limit = app._config.control_room.history_limit
    if len(app._saved_state.history) > limit:
        app._saved_state.history = app._saved_state.history[-limit:]

    app._history = [item.raw for item in app._saved_state.history if item.raw]
    app._history_pos = len(app._history)
    app._history_draft = ""
    save_saved_state(app)
