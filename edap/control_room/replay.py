from __future__ import annotations

from typing import Protocol

from rich.markup import escape
from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Input, OptionList, RichLog, Static

from edap.config import AppConfig
from edap.control_room import history as _history
from edap.control_room.models import ReplaySelection
from edap.control_room_state import CommandHistoryEntry, ControlRoomState


class ReplayHost(Protocol):
    _config: AppConfig
    _saved_state: ControlRoomState
    _resume_entries: list[ReplaySelection]
    _resume_open: bool
    _resume_filter: str
    _haul_params: dict[str, str]

    def _log(self, msg: str) -> None: ...
    def _save_saved_state(self) -> None: ...
    def _dispatch_command(self, raw: str) -> None: ...
    def _dispatch_haul_loop(self) -> None: ...
    def _dispatch_dest(self, destination: str, galaxy_map_settle: float) -> None: ...
    def _start_haul_prompt(
        self,
        *,
        commodity: str,
        prompt_for_commodity: bool,
        seed: dict[str, str] | None = None,
    ) -> None: ...
    def _start_dest_prompt(self, destination: str, *, settle_default: float | None = None) -> None: ...
    def set_focus(self, widget: object) -> None: ...
    def query_one(self, selector: str, widget_type: object | None = None) -> object: ...


def default_haul_matches(app: ReplayHost, entry: CommandHistoryEntry) -> bool:
    return _history.default_haul_matches(entry, app._saved_state.default_haul)


def filtered_resume_entries(app: ReplayHost) -> list[ReplaySelection]:
    return _history.filtered_resume_entries(
        app._saved_state.history,
        app._saved_state.default_haul,
        app._resume_filter,
    )


def refresh_resume_help(app: ReplayHost) -> None:
    filter_label = app._resume_filter or "none"
    help_text = (
        "Replay history  |  Enter execute  |  e edit  |  * set default haul  |  "
        "type prefix filter  |  Backspace delete  |  Esc/q close\n"
        f"Filter: {filter_label}"
    )
    app.query_one("#resume-help", Static).update(help_text)


def show_resume_picker(app: ReplayHost) -> None:
    if not app._saved_state.history:
        app._log("[dim]No saved command history yet.[/]")
        return

    app._resume_filter = ""
    app._resume_entries = filtered_resume_entries(app)
    option_list = app.query_one("#resume-list", OptionList)
    option_list.clear_options()
    option_list.add_options([item.label for item in app._resume_entries])
    if app._resume_entries:
        option_list.highlighted = 0
    app._resume_open = True
    app.query_one("#activity", RichLog).styles.display = "none"
    app.query_one("#resume-browser", Vertical).styles.display = "block"
    refresh_resume_help(app)
    update_resume_detail(app)
    app.set_focus(option_list)


def refresh_resume_picker(app: ReplayHost) -> None:
    if not app._resume_open:
        return
    option_list = app.query_one("#resume-list", OptionList)
    highlighted = option_list.highlighted or 0
    app._resume_entries = filtered_resume_entries(app)
    option_list.clear_options()
    option_list.add_options([item.label for item in app._resume_entries])
    if app._resume_entries:
        option_list.highlighted = min(highlighted, len(app._resume_entries) - 1)
    refresh_resume_help(app)
    update_resume_detail(app)


def close_resume_picker(app: ReplayHost) -> None:
    app._resume_open = False
    app._resume_filter = ""
    app.query_one("#resume-browser", Vertical).styles.display = "none"
    app.query_one("#activity", RichLog).styles.display = "block"
    app.set_focus(app.query_one("#cmd", Input))


def selected_resume_entry(app: ReplayHost) -> CommandHistoryEntry | None:
    if not app._resume_entries:
        return None
    option_list = app.query_one("#resume-list", OptionList)
    index = option_list.highlighted
    if index is None or index < 0 or index >= len(app._resume_entries):
        return None
    return app._resume_entries[index].entry


def update_resume_detail(app: ReplayHost) -> None:
    detail = "[dim]No selection[/]"
    entry = selected_resume_entry(app)
    if entry is not None:
        detail = escape(_history.resume_detail(entry))
    app.query_one("#resume-detail", Static).update(Text.from_markup(detail))


def resume_execute_selected(app: ReplayHost) -> None:
    entry = selected_resume_entry(app)
    if entry is None:
        return
    close_resume_picker(app)
    replay_history_entry(app, entry, edit=False)


def resume_edit_selected(app: ReplayHost) -> None:
    entry = selected_resume_entry(app)
    if entry is None:
        return
    close_resume_picker(app)
    replay_history_entry(app, entry, edit=True)


def resume_toggle_default_selected(app: ReplayHost) -> None:
    entry = selected_resume_entry(app)
    if entry is None:
        return
    if entry.command != "haul":
        app._log("[dim]Only haul entries can be saved as the default.[/]")
        return
    if default_haul_matches(app, entry):
        app._saved_state.default_haul = {}
        app._log("[dim]Cleared saved default haul.[/]")
    else:
        app._saved_state.default_haul = {
            str(key): str(value) for key, value in entry.params.items()
        }
        commodity = app._saved_state.default_haul.get("commodity", "haul")
        app._log(f"[dim]Saved default haul from history: {escape(commodity)}[/]")
    app._save_saved_state()
    refresh_resume_picker(app)


def replay_history_entry(
    app: ReplayHost,
    entry: CommandHistoryEntry,
    *,
    edit: bool,
) -> None:
    if edit:
        if entry.command == "haul":
            app._start_haul_prompt(
                commodity="",
                prompt_for_commodity=True,
                seed={str(key): str(value) for key, value in entry.params.items()},
            )
            return
        if entry.command == "dest":
            destination = str(entry.params.get("destination", "")).strip()
            if destination:
                settle_value = entry.params.get("galaxy_map_settle")
                settle_default = float(settle_value) if settle_value is not None else None
                app._start_dest_prompt(destination, settle_default=settle_default)
                return
        cmd_input = app.query_one("#cmd", Input)
        cmd_input.value = entry.raw
        cmd_input.cursor_position = len(cmd_input.value)
        app.set_focus(cmd_input)
        return

    if entry.command == "haul":
        app._haul_params = {str(key): str(value) for key, value in entry.params.items()}
        app._dispatch_haul_loop()
        return
    if entry.command == "dest":
        destination = str(entry.params.get("destination", "")).strip()
        if destination:
            settle_value = entry.params.get("galaxy_map_settle")
            settle = (
                float(settle_value)
                if settle_value is not None
                else app._config.controls.galaxy_map_settle_seconds
            )
            app._dispatch_dest(destination, settle)
        return

    app._dispatch_command(entry.raw)
