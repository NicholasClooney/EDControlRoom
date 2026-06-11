"""
ED AutoPilot Control Room

Live TUI: ship status, activity log, market tracker, and routine dispatch.

Usage:
    uv run python3 control_room.py
    uv run python3 control_room.py --market aluminium

Routine commands (type in the input bar):
    dock               dock + auto-refuel/repair; skips supercruise-exit wait if already in normal space
    undock             launch from station
    boost              fire boost three times immediately
    escape             set speed full, then boost until Status.json says mass lock cleared
    buy <item> [N]     buy N units (default MAX) of commodity
    sell [item] [N]    sell commodity (default: market filter); amount default MAX
    jump               FSD jump sequence
    haul [commodity]   start haul loop; prompts for commodity/stations if not provided
    multi_leg_haul <route.json|spansh-url>   run a standalone multi-leg haul route
    dest <system>      open galaxy map and plot a route to the named system
    set_dest <system>  alias for dest

Market commands:
    market filter <name>   filter market panel by commodity name (e.g. market filter aluminium)
    market [clear]         clear the filter (default when no args)
    market lock            freeze panel to current station
    market unlock          unfreeze panel

Other:
    commands           list supported commands
    help [command]     explain a command in plain English
    replay             open the replay history browser
    q / quit           cancel active work if needed, then exit
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path
from typing import IO, Any, Callable, Protocol

from rich.markup import escape
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import MouseScrollDown, MouseScrollUp
from textual.widgets import Footer, Header, Input, OptionList, RichLog, Static

from edap.config import AppConfig
from edap.control_room import (
    bootstrap as _bootstrap,
    commands as _commands,
    error_text,
    events as _events,
    facade as _facade,
    haul_tracking as _haul_tracking,
    help as _help,
    history as _history,
    persistence as _persistence,
    prompts as _prompts,
    replay as _replay,
    rendering as _rendering,
    tts as _tts_module,
    routines_haul,
    routines_movement,
    routines_nav,
    routines_station,
    routines_trade,
    workers as _workers,
)
from edap.control_room.models import (
    HaulStats,
    HistoryState,
    MarketData,
    PromptState,
    ReplayBrowserState,
    ReplaySelection,
    RuntimeUIState,
    ShipState,
)

# Modules eligible for in-place hot reload via the `reload` command.
# Order matters: leaf modules first, then modules that import from them.
_RELOADABLE_MODULES = [
    routines_haul,
    routines_trade,
    routines_nav,
    routines_movement,
    routines_station,
    _bootstrap,
    _events,
    _facade,
    _haul_tracking,
    _history,
    _help,
    _commands,
    _persistence,
    _prompts,
    _replay,
    _rendering,
    _tts_module,
    _workers,
]
from edap.control_room_state import (
    CommandHistoryEntry,
    ControlRoomState,
)
from edap.binding_names import format_binding_action_hint
from edap.runtime import RuntimeContext, build_runtime_context, load_config_with_fallback
from edap.ship_controls import DEFAULT_SHIP_CONTROL_ACTIONS, ShipControls
from edap.tts import AnnouncementId, TTSAnnouncer, format_credits_short
from edap import version as _version


# ── All actions needed across every supported routine ──────────────────────────

_ALL_ROUTINE_ACTIONS = list(DEFAULT_SHIP_CONTROL_ACTIONS)
_STARTUP_BINDING_WARNING_IGNORED_ACTIONS = frozenset({
    "RollLeftButton",
    "RollRightButton",
    "PitchUpButton",
    "PitchDownButton",
    "YawLeftButton",
    "YawRightButton",
})

_DEFAULT_COMMAND_PLACEHOLDER = "commands | help dock | replay | dock | undock | boost | escape | jump | buy <item> [N] | sell [item] | haul [commodity] | multi_leg_haul <route> | dest <system> | market ... | reload | q"
_ACTIVITY_AUTO_FOLLOW_DEBOUNCE_SECONDS = 10.0
_JOURNAL_ARTIFACT_LOG_PATH = Path("artifacts/control-room.log")
_JOURNAL_ARTIFACT_LOG_BUFFER_SIZE = 8192
_JOURNAL_ARTIFACT_LOG_FLUSH_EVERY = 20

_RoutineCancelled = _workers.RoutineCancelled
_CancellationProxy = _workers.CancellationProxy


# ── Helpers ────────────────────────────────────────────────────────────────────


def _fmt_cr(n: int) -> str:
    return _rendering.fmt_cr(n)


def _fuel_bar(level: float, capacity: float) -> str:
    return _rendering.fuel_bar(level, capacity)


def _loc(item: dict[str, Any], key: str) -> str:
    return _rendering.loc(item, key)


def _hhmmss() -> str:
    return _rendering.hhmmss()


def _is_recent(ev: dict[str, Any], threshold_s: float = 120.0) -> bool:
    return _rendering.is_recent(ev, threshold_s=threshold_s)


def _fmt_duration(seconds: float | None) -> str:
    return _rendering.fmt_duration(seconds)


def _build_log_text(msg: str) -> Text:
    return _rendering.build_log_text(msg)


def _read_cargo_inventory(journal_dir: Path) -> list[dict[str, Any]]:
    return _rendering.read_cargo_inventory(journal_dir)


def _cargo_summary_lines(inventory: list[dict[str, Any]], *, limit: int = 3) -> list[str]:
    return _rendering.cargo_summary_lines(inventory, limit=limit)


class VersionSource(Protocol):
    def get_current_version(self) -> str: ...

    def fetch_latest_github_release(self) -> _version.GitHubRelease | None: ...


class DefaultVersionSource:
    def get_current_version(self) -> str:
        return _version.get_current_version()

    def fetch_latest_github_release(self) -> _version.GitHubRelease | None:
        return _version.fetch_latest_github_release()


class ActivityLog(RichLog):
    def __init__(
        self,
        *,
        max_lines: int | None = None,
        pause_seconds: float = _ACTIVITY_AUTO_FOLLOW_DEBOUNCE_SECONDS,
        time_fn: Callable[[], float] | None = None,
        on_pause_changed: Callable[[bool], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(max_lines=max_lines, **kwargs)
        self._pause_seconds = pause_seconds
        self._time_fn = time_fn or time.monotonic
        self._on_pause_changed = on_pause_changed
        self._resume_timer: Any | None = None

    @property
    def auto_follow_paused(self) -> bool:
        return not self.auto_scroll

    def configure_auto_follow(
        self,
        *,
        time_fn: Callable[[], float] | None = None,
        on_pause_changed: Callable[[bool], None] | None = None,
    ) -> None:
        if time_fn is not None:
            self._time_fn = time_fn
        if on_pause_changed is not None:
            self._on_pause_changed = on_pause_changed

    def _set_auto_follow_paused(self, paused: bool) -> None:
        if paused == self.auto_follow_paused:
            if paused:
                self._schedule_resume_timer()
            return
        self.auto_scroll = not paused
        if paused:
            self._schedule_resume_timer()
        else:
            self._cancel_resume_timer()
        if self._on_pause_changed is not None:
            self._on_pause_changed(paused)

    def _schedule_resume_timer(self) -> None:
        self._cancel_resume_timer()
        self._resume_timer = self.set_timer(
            self._pause_seconds,
            self.resume_auto_follow,
        )

    def _cancel_resume_timer(self) -> None:
        if self._resume_timer is None:
            return
        self._resume_timer.stop()
        self._resume_timer = None

    def resume_auto_follow(self) -> None:
        self._set_auto_follow_paused(False)

    def sync_auto_follow_to_scroll_position(self) -> None:
        if self.scroll_y >= self.max_scroll_y:
            self.resume_auto_follow()
            return
        self._set_auto_follow_paused(True)

    def on_mouse_scroll_up(self, event: MouseScrollUp) -> None:
        super()._on_mouse_scroll_up(event)
        self.sync_auto_follow_to_scroll_position()

    def on_mouse_scroll_down(self, event: MouseScrollDown) -> None:
        super()._on_mouse_scroll_down(event)
        self.sync_auto_follow_to_scroll_position()

    def action_scroll_up(self) -> None:
        super().action_scroll_up()
        self.sync_auto_follow_to_scroll_position()

    def action_scroll_down(self) -> None:
        super().action_scroll_down()
        self.sync_auto_follow_to_scroll_position()

    def action_page_up(self) -> None:
        super().action_page_up()
        self.sync_auto_follow_to_scroll_position()

    def action_page_down(self) -> None:
        super().action_page_down()
        self.sync_auto_follow_to_scroll_position()

    def action_scroll_home(self) -> None:
        super().action_scroll_home()
        self.sync_auto_follow_to_scroll_position()

    def action_scroll_end(self) -> None:
        super().action_scroll_end()
        self.sync_auto_follow_to_scroll_position()


# ── App ────────────────────────────────────────────────────────────────────────


class ControlRoomApp(App[None]):
    BINDINGS = [
        ("ctrl+c", "request_quit", "Quit"),
        ("ctrl+d", "request_quit", "Quit"),
        ("ctrl+r", "open_history", "History"),
    ]

    CSS = """
    Screen  { layout: vertical; }
    #main   { height: 1fr; }
    #left   { width: 58%; }
    #right  { width: 42%; }
    #status {
        height: auto;
        max-height: 14;
        border: solid $primary;
        padding: 0 1;
    }
    #activity-pane {
        height: 1fr;
    }
    #activity {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    #haul {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    #market {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    #cmd { height: 3; }
    #resume-browser {
        display: none;
        height: 1fr;
        border: heavy $primary;
        padding: 1;
    }
    #resume-help {
        height: auto;
        padding: 0 0 1 0;
    }
    #resume-list {
        height: 1fr;
        border: solid $accent;
    }
    #resume-detail {
        height: 6;
        border: solid $primary;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    """

    def __init__(
        self,
        ctx: RuntimeContext,
        market_filter: str | None = None,
        *,
        activity_log_max_lines: int | None = None,
        version_source: VersionSource | None = None,
    ) -> None:
        super().__init__()
        self._ctx = ctx
        self._config: AppConfig = ctx.config
        self._journal_dir: Path = ctx.journal.effective_path  # type: ignore[assignment]
        self._market_path = self._journal_dir / "Market.json"
        self._ship = ShipState()
        self._market = MarketData()
        self._haul_stats = HaulStats()
        self._market_filter = market_filter
        self._market_mtime: float | None = None
        self._controls: ShipControls | None = None
        self._runtime_state = RuntimeUIState()
        self._prompt_state = PromptState()
        self._history_state = HistoryState()
        self._state_path: Path = self._config.control_room.state_file
        self._activity_log_max_lines = (
            self._config.control_room.activity_log_max_lines
            if activity_log_max_lines is None
            else activity_log_max_lines
        )
        self._journal_artifact_log_path = _JOURNAL_ARTIFACT_LOG_PATH
        self._journal_artifact_log_handle: IO[str] | None = None
        self._journal_artifact_log_pending_writes = 0
        self._saved_state = ControlRoomState()
        self._replay_state = ReplayBrowserState()
        self._watcher_worker: Any | None = None
        self._routine_worker: Any | None = None
        self._time_fn: Callable[[], float] = time.monotonic
        self._tts = TTSAnnouncer(self._config.tts, platform_name=self._config.runtime.platform)
        self._version_source = version_source or DefaultVersionSource()
        self._current_version = self._version_source.get_current_version()
        self._facade = _facade.ControlRoomFacade(
            self,
            default_placeholder=_DEFAULT_COMMAND_PLACEHOLDER,
            reloadable_modules=_RELOADABLE_MODULES,
        )

    def __getattr__(self, name: str) -> Any:
        target = _facade.FACADE_METHOD_MAP.get(name)
        if target is None:
            raise AttributeError(name)
        return getattr(self._facade, target)

    @property
    def _haul_params(self) -> dict[str, str]:
        return self._prompt_state.haul_params

    @_haul_params.setter
    def _haul_params(self, value: dict[str, str]) -> None:
        self._prompt_state.haul_params = value

    @property
    def _haul_prompt_defaults(self) -> dict[str, str]:
        return self._prompt_state.haul_prompt_defaults

    @_haul_prompt_defaults.setter
    def _haul_prompt_defaults(self, value: dict[str, str]) -> None:
        self._prompt_state.haul_prompt_defaults = value

    @property
    def _haul_prompt_step(self) -> str:
        return self._prompt_state.haul_prompt_step

    @_haul_prompt_step.setter
    def _haul_prompt_step(self, value: str) -> None:
        self._prompt_state.haul_prompt_step = value

    @property
    def _haul_confirm_buy_station(self) -> str:
        return self._prompt_state.haul_confirm_buy_station

    @_haul_confirm_buy_station.setter
    def _haul_confirm_buy_station(self, value: str) -> None:
        self._prompt_state.haul_confirm_buy_station = value

    @property
    def _haul_prompt_raw_command(self) -> str:
        return self._prompt_state.haul_prompt_raw_command

    @_haul_prompt_raw_command.setter
    def _haul_prompt_raw_command(self, value: str) -> None:
        self._prompt_state.haul_prompt_raw_command = value

    @property
    def _haul_prompt_skip_delay(self) -> bool:
        return self._prompt_state.haul_prompt_skip_delay

    @_haul_prompt_skip_delay.setter
    def _haul_prompt_skip_delay(self, value: bool) -> None:
        self._prompt_state.haul_prompt_skip_delay = value

    @property
    def _dest_prompt_destination(self) -> str:
        return self._prompt_state.dest_prompt_destination

    @_dest_prompt_destination.setter
    def _dest_prompt_destination(self, value: str) -> None:
        self._prompt_state.dest_prompt_destination = value

    @property
    def _dest_prompt_settle_default(self) -> float | None:
        return self._prompt_state.dest_prompt_settle_default

    @_dest_prompt_settle_default.setter
    def _dest_prompt_settle_default(self, value: float | None) -> None:
        self._prompt_state.dest_prompt_settle_default = value

    @property
    def _dest_prompt_raw_command(self) -> str:
        return self._prompt_state.dest_prompt_raw_command

    @_dest_prompt_raw_command.setter
    def _dest_prompt_raw_command(self, value: str) -> None:
        self._prompt_state.dest_prompt_raw_command = value

    @property
    def _dest_prompt_skip_delay(self) -> bool:
        return self._prompt_state.dest_prompt_skip_delay

    @_dest_prompt_skip_delay.setter
    def _dest_prompt_skip_delay(self, value: bool) -> None:
        self._prompt_state.dest_prompt_skip_delay = value

    @property
    def _history(self) -> list[str]:
        return self._history_state.entries

    @_history.setter
    def _history(self, value: list[str]) -> None:
        self._history_state.entries = value

    @property
    def _history_pos(self) -> int:
        return self._history_state.pos

    @_history_pos.setter
    def _history_pos(self, value: int) -> None:
        self._history_state.pos = value

    @property
    def _history_draft(self) -> str:
        return self._history_state.draft

    @_history_draft.setter
    def _history_draft(self, value: str) -> None:
        self._history_state.draft = value

    @property
    def _resume_entries(self) -> list[ReplaySelection]:
        return self._replay_state.entries

    @_resume_entries.setter
    def _resume_entries(self, value: list[ReplaySelection]) -> None:
        self._replay_state.entries = value

    @property
    def _resume_open(self) -> bool:
        return self._replay_state.open

    @_resume_open.setter
    def _resume_open(self, value: bool) -> None:
        self._replay_state.open = value

    @property
    def _resume_filter(self) -> str:
        return self._replay_state.filter_text

    @_resume_filter.setter
    def _resume_filter(self, value: str) -> None:
        self._replay_state.filter_text = value

    @property
    def _routine_active(self) -> bool:
        return self._runtime_state.routine_active

    @_routine_active.setter
    def _routine_active(self, value: bool) -> None:
        self._runtime_state.routine_active = value

    @property
    def _active_routine_name(self) -> str | None:
        return self._runtime_state.active_routine_name

    @_active_routine_name.setter
    def _active_routine_name(self, value: str | None) -> None:
        self._runtime_state.active_routine_name = value

    @property
    def _haul_stop_requested(self) -> bool:
        return self._runtime_state.haul_stop_requested

    @_haul_stop_requested.setter
    def _haul_stop_requested(self, value: bool) -> None:
        self._runtime_state.haul_stop_requested = value

    @property
    def _verbose_controls(self) -> bool:
        return self._runtime_state.verbose_controls

    @_verbose_controls.setter
    def _verbose_controls(self, value: bool) -> None:
        self._runtime_state.verbose_controls = value

    @property
    def _instant_mode(self) -> bool:
        return self._runtime_state.instant_mode

    @_instant_mode.setter
    def _instant_mode(self, value: bool) -> None:
        self._runtime_state.instant_mode = value

    @property
    def _sigint_pending(self) -> bool:
        return self._runtime_state.sigint_pending

    @_sigint_pending.setter
    def _sigint_pending(self, value: bool) -> None:
        self._runtime_state.sigint_pending = value

    @property
    def _shutdown_requested(self) -> bool:
        return self._runtime_state.shutdown_requested

    @_shutdown_requested.setter
    def _shutdown_requested(self, value: bool) -> None:
        self._runtime_state.shutdown_requested = value

    @property
    def _shutdown_finalized(self) -> bool:
        return self._runtime_state.shutdown_finalized

    @_shutdown_finalized.setter
    def _shutdown_finalized(self, value: bool) -> None:
        self._runtime_state.shutdown_finalized = value

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static(id="status")
                with Vertical(id="activity-pane"):
                    yield ActivityLog(
                        id="activity",
                        markup=True,
                        highlight=True,
                        wrap=True,
                        max_lines=self._activity_log_max_lines,
                    )
                    with Vertical(id="resume-browser"):
                        yield Static(
                            "Replay history  |  Enter execute  |  ! execute now  |  e edit  |  * set default haul  |  Esc/q close",
                            id="resume-help",
                        )
                        yield OptionList(id="resume-list")
                        yield Static(id="resume-detail")
            with Vertical(id="right"):
                yield Static(id="market")
                yield Static(id="haul")
        yield Input(placeholder=_DEFAULT_COMMAND_PLACEHOLDER, id="cmd")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "ED Control Room"
        self.query_one("#status", Static).border_title = "SHIP STATUS"
        self.query_one("#activity", ActivityLog).configure_auto_follow(
            time_fn=lambda: self._time_fn(),
            on_pause_changed=lambda paused: self._refresh_activity_title(),
        )
        self._refresh_activity_title()
        self.query_one("#resume-browser", Vertical).border_title = "REPLAY HISTORY"
        self.query_one("#haul", Static).border_title = "HAUL"
        self.query_one("#market", Static).border_title = "MARKET"
        self._build_controls()
        self._log_bindings_status()
        self._load_saved_state()
        self._log_startup_modes()
        self._start_update_check()
        self._bootstrap_ship_state()
        self._load_market_json()
        self._refresh_status()
        self._refresh_haul_stats()
        self._refresh_market()
        self._watcher_worker = self._start_watcher()
        self.set_interval(0.1, self._drain_pending_sigint)
        self.set_focus(self.query_one("#cmd", Input))
        self._update_resume_detail()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _build_controls(self) -> None:
        if self._ctx.binding_lookup is None or self._ctx.input_controller is None:
            self._log("[yellow]Bindings not loaded — routine commands (dock/undock/buy/sell) unavailable[/]")
            return
        self._controls = ShipControls.from_binding_lookup(
            self._ctx.binding_lookup,
            self._ctx.input_controller,
            minimum_action_hold_s=self._config.controls.minimum_action_hold_seconds,
            continuous_action_hold_s=self._config.controls.continuous_action_hold_seconds,
        )

    def _load_saved_state(self) -> None:
        _persistence.load_saved_state(self)

    def _log_bindings_status(self) -> None:
        bindings_path = self._ctx.bindings.effective.get("path")
        bindings_source = self._ctx.bindings.cli_source_status()
        reason = self._ctx.bindings.effective.get("reason", "unknown")

        if bindings_path:
            self._log(
                f"[dim]Bindings file: {escape(str(bindings_path))} "
                f"(source: {escape(bindings_source)})[/]"
            )
        else:
            self._log(
                f"[yellow]Bindings file unavailable "
                f"(source: {escape(bindings_source)}; reason: {escape(str(reason))})[/]"
            )

        if self._ctx.binding_lookup is None:
            return

        issues = {
            action: result
            for action, result in self._ctx.binding_lookup.issues().items()
            if action not in _STARTUP_BINDING_WARNING_IGNORED_ACTIONS
        }
        if not issues:
            return

        self._log(
            f"[yellow]Bindings warning — {len(issues)} routine action(s) "
            "have no usable keyboard mapping.[/]"
        )
        for action, result in sorted(issues.items()):
            reason = result.reason or result.status
            hint = format_binding_action_hint(action)
            self._log(
                f"[yellow]- {escape(action)} -> {escape(hint)}: {escape(reason)}[/]"
            )

    def _save_saved_state(self) -> None:
        _persistence.save_saved_state(self)

    def _log_startup_modes(self) -> None:
        state = "on" if self._instant_mode else "off"
        self._log(f"[dim]Instant mode {state} — control with: instant[/]")

    def _start_update_check(self) -> None:
        if not self._config.control_room.check_for_updates:
            self._log_current_version(is_latest=None)
            return
        self._check_for_updates()

    def _log_current_version(self, *, is_latest: bool | None) -> None:
        current = _version.display_version(self._current_version)
        if is_latest is True:
            self._log(
                f"[dim]Currently running latest version "
                f"(*{escape(current)}*) of {_version.PROJECT_DISPLAY_NAME}[/]"
            )
            return
        self._log(
            f"[dim]Currently running version *{escape(current)}* of {_version.PROJECT_DISPLAY_NAME}[/]"
        )

    def _log_update_available(self, release: _version.GitHubRelease) -> None:
        self._log(
            f"[yellow]A newer {_version.PROJECT_DISPLAY_NAME} release is available: "
            f"{escape(release.display_name)}[/]"
        )
        self._log_current_version(is_latest=False)
        self._log(f"[dim]{escape(release.html_url)}[/]")

    def _bootstrap_ship_state(self) -> None:
        _bootstrap.bootstrap_ship_state(self)
        self._tts.set_commander_name(self._ship.commander)

    def _sync_status_snapshot(self) -> None:
        _bootstrap.sync_status_snapshot(self)

    # ── Rendering ──────────────────────────────────────────────────────────────

    def _refresh_status(self) -> None:
        self.query_one("#status", Static).update(
            Text.from_markup(_rendering.status_markup(self._ship))
        )

    def _refresh_haul_stats(self) -> None:
        widget = self.query_one("#haul", Static)
        widget.update(Text.from_markup(
            _rendering.haul_stats_markup(
                self._haul_stats,
                current_balance=self._ship.credits,
                now_fn=self._time_fn,
            )
        ))

    def _refresh_market(self) -> None:
        self.query_one("#market", Static).update(
            Text.from_markup(_rendering.market_markup(self._market, self._market_filter))
        )

    def _activity_auto_follow_paused(self) -> bool:
        return self.query_one("#activity", ActivityLog).auto_follow_paused

    def _refresh_activity_title(self) -> None:
        title = "ACTIVITY"
        if self._activity_auto_follow_paused():
            title += " • AUTO-FOLLOW PAUSED"
        self.query_one("#activity", ActivityLog).border_title = title

    def _log(self, msg: str) -> None:
        activity = self.query_one("#activity", ActivityLog)
        activity.write(_build_log_text(msg))
        self._refresh_activity_title()

    def _start_haul_stats(
        self,
        *,
        station_1_buying: str,
        station_2_buying: str,
        station_1: str,
        station_2: str,
    ) -> None:
        _haul_tracking.start_haul_stats(
            self,
            station_1_buying=station_1_buying,
            station_2_buying=station_2_buying,
            station_1=station_1,
            station_2=station_2,
        )

    def _stop_haul_stats(self) -> None:
        _haul_tracking.stop_haul_stats(self)

    def _finalize_completed_haul_run(self) -> None:
        _haul_tracking.finalize_completed_haul_run(self)

    def _handle_haul_event(self, ev: dict[str, Any], *, station_before: str | None) -> None:
        _haul_tracking.handle_haul_event(self, ev, station_before=station_before)

    def _announce_tts(self, message_id: AnnouncementId, /, **values: object) -> None:
        self._tts.announce(message_id, **values)

    def _announce_tts_for_event(self, ev: dict[str, Any], *, station_before: str | None) -> None:
        event = str(ev.get("event", ""))
        if event == "FSDTarget":
            system_name = str(ev.get("Name", "")).strip()
            if system_name:
                self._announce_tts(AnnouncementId.DESTINATION_SET, system_name=system_name)
        elif event == "Docked":
            self._announce_tts(AnnouncementId.DOCKING_COMPLETE)
        elif event == "Undocked" and station_before and self._haul_stats.active:
            self._announce_tts(AnnouncementId.UNDOCKING)
        elif event == "StartJump" and str(ev.get("JumpType", "")).lower() == "hyperspace":
            system_name = str(ev.get("StarSystem", "")).strip() or str(self._ship.target or "").strip()
            if system_name:
                self._announce_tts(AnnouncementId.JUMP_INITIATED, system_name=system_name)
        elif event == "FSDJump":
            system_name = str(ev.get("StarSystem", "")).strip()
            if system_name:
                self._announce_tts(AnnouncementId.ARRIVAL, system_name=system_name)
        elif event == "SupercruiseExit":
            station_name = (
                str(ev.get("StationName", "")).strip()
                or str(ev.get("Body", "")).strip()
                or str(ev.get("BodyName", "")).strip()
            )
            if station_name:
                self._announce_tts(AnnouncementId.APPROACHING_STATION, station_name=station_name)
        elif event == "MarketBuy":
            self._announce_tts(AnnouncementId.CARGO_LOADED)
        elif event == "MarketSell" and "TotalSale" in ev:
            self._announce_tts(
                AnnouncementId.SALE_PROFIT,
                profit_short=format_credits_short(int(ev["TotalSale"])),
            )

    def _default_haul_matches(self, entry: CommandHistoryEntry) -> bool:
        return _replay.default_haul_matches(self, entry)

    def _resume_label(self, entry: CommandHistoryEntry) -> str:
        return _history.resume_label(entry, self._saved_state.default_haul)

    def _filtered_resume_entries(self) -> list[ReplaySelection]:
        return _replay.filtered_resume_entries(self)

    def _refresh_resume_help(self) -> None:
        _replay.refresh_resume_help(self)

    def _selected_resume_entry(self) -> CommandHistoryEntry | None:
        return _replay.selected_resume_entry(self)

    def _update_resume_detail(self) -> None:
        _replay.update_resume_detail(self)

    def _replay_history_entry(
        self,
        entry: CommandHistoryEntry,
        *,
        edit: bool,
        skip_delay: bool = False,
    ) -> None:
        _replay.replay_history_entry(self, entry, edit=edit, skip_delay=skip_delay)

    # ── Market JSON ────────────────────────────────────────────────────────────

    # ── Journal event processing ───────────────────────────────────────────────

    def _handle_event(self, ev: dict[str, Any]) -> None:
        self._append_journal_event(ev)
        event = ev.get("event", "")
        station_before = self._ship.station
        _events.apply_ship_event(self._ship, ev)
        self._tts.set_commander_name(self._ship.commander)
        self._sync_status_snapshot()

        msg = self._activity_line(ev)
        if msg:
            self._log(msg)

        if event == "Docked":
            self._load_market_json()

        self._refresh_status()
        self._handle_haul_event(ev, station_before=station_before)
        self._announce_tts_for_event(ev, station_before=station_before)

    def _activity_line(self, ev: dict[str, Any]) -> str | None:
        return _rendering.activity_line(ev)

    # ── Background status watcher ──────────────────────────────────────────────

    @work(thread=True, group="watchers", exclusive=True)
    def _start_watcher(self) -> None:
        _workers.start_watcher_loop(self)

    @work(thread=True, group="watchers", exclusive=False)
    def _check_for_updates(self) -> None:
        release = self._version_source.fetch_latest_github_release()
        if release is None:
            self.call_from_thread(self._log_current_version, is_latest=None)
            return
        if not _version.is_newer_version(release.version, self._current_version):
            self.call_from_thread(self._log_current_version, is_latest=True)
            return
        self.call_from_thread(self._log_update_available, release)

    # ── Routine dispatch ───────────────────────────────────────────────────────

    @work(thread=True, group="routines", exclusive=True)
    def _run_in_thread(self, fn: Callable[[], RoutineResult | None]) -> None:
        _workers.run_routine_thread(self, fn)

    def _clear_routine(self) -> None:
        _workers.clear_routine(self)

    # ── Quit ───────────────────────────────────────────────────────────────────

    def action_request_quit(self) -> None:
        if self._routine_active and self._routine_worker is not None:
            self._cancel_active_routine("Ctrl-C / Ctrl-D")
            return
        self._request_shutdown("Ctrl-C / Ctrl-D")

    def request_sigint(self) -> None:
        self._sigint_pending = True

    def _drain_pending_sigint(self) -> None:
        if not self._sigint_pending:
            return
        self._sigint_pending = False
        self.action_request_quit()

    def _cancel_active_routine(self, source: str) -> None:
        if self._active_routine_name == "haul" and not self._haul_stop_requested:
            self._haul_stop_requested = True
            self._log(
                f"[yellow]{escape(source)} received — haul will stop after this run at station 1 before a new cycle.[/]"
            )
            self._announce_tts(AnnouncementId.HAUL_STOP_AFTER_RUN)
            return
        if self._active_routine_name == "multi_leg_haul" and not self._haul_stop_requested:
            self._haul_stop_requested = True
            self._log(
                f"[yellow]{escape(source)} received — multi-leg haul will stop at the next station boundary before departure.[/]"
            )
            return
        if self._active_routine_name == "haul" and self._haul_stop_requested:
            self._haul_stop_requested = False
            self._log(f"[yellow]{escape(source)} received again — cancelling haul immediately.[/]")
        elif self._active_routine_name == "multi_leg_haul" and self._haul_stop_requested:
            self._haul_stop_requested = False
            self._log(f"[yellow]{escape(source)} received again — cancelling multi-leg haul immediately.[/]")
        else:
            self._log(f"[yellow]{escape(source)} received — cancelling active routine.[/]")
        self._routine_worker.cancel()

    def _clear_pending_haul_stop(self) -> None:
        self._haul_stop_requested = False

    def _request_shutdown(self, source: str) -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        self._log(f"[yellow]{escape(source)} received — exiting control room.[/]")
        self._finalize_shutdown()

    def _append_journal_event(self, ev: dict[str, Any]) -> None:
        handle = self._ensure_journal_artifact_log_handle()
        if handle is None:
            return
        handle.write(json.dumps(ev))
        handle.write("\n")
        self._journal_artifact_log_pending_writes += 1
        if self._journal_artifact_log_pending_writes >= _JOURNAL_ARTIFACT_LOG_FLUSH_EVERY:
            self._flush_journal_artifact_log()

    def _ensure_journal_artifact_log_handle(self) -> IO[str] | None:
        if self._journal_artifact_log_handle is not None:
            return self._journal_artifact_log_handle
        try:
            self._journal_artifact_log_path.parent.mkdir(parents=True, exist_ok=True)
            self._journal_artifact_log_handle = self._journal_artifact_log_path.open(
                "a",
                encoding="utf-8",
                buffering=_JOURNAL_ARTIFACT_LOG_BUFFER_SIZE,
            )
        except OSError:
            return None
        return self._journal_artifact_log_handle

    def _flush_journal_artifact_log(self) -> None:
        handle = self._journal_artifact_log_handle
        if handle is None or self._journal_artifact_log_pending_writes == 0:
            return
        try:
            handle.flush()
        except OSError:
            return
        self._journal_artifact_log_pending_writes = 0

    def _finalize_shutdown(self) -> None:
        if self._shutdown_finalized:
            return
        self._shutdown_finalized = True
        if self._journal_artifact_log_handle is not None:
            self._flush_journal_artifact_log()
            try:
                self._journal_artifact_log_handle.close()
            except OSError:
                pass
            self._journal_artifact_log_handle = None
            self._journal_artifact_log_pending_writes = 0
        self._tts.close()
        self.workers.cancel_group(self, "watchers")
        self.workers.cancel_group(self, "routines")
        self.exit()

    def action_open_history(self) -> None:
        if self._haul_prompt_step or self._haul_confirm_buy_station or self._dest_prompt_destination:
            return
        if self._resume_open:
            self._close_resume_picker()
            return
        self._show_resume_picker()

    # ── Command input ──────────────────────────────────────────────────────────

    def on_key(self, event) -> None:
        """Handle up/down arrow keys for readline-style command history."""
        if event.key == "ctrl+d":
            event.prevent_default()
            self.action_request_quit()
            return
        if self._resume_open:
            if event.key == "escape" or (event.key == "q" and not self._resume_filter):
                event.prevent_default()
                self._close_resume_picker()
            elif event.key == "e" and not self._resume_filter:
                event.prevent_default()
                self._resume_edit_selected()
            elif event.character == "!":
                event.prevent_default()
                self._resume_execute_selected_immediate()
            elif event.character == "*":
                event.prevent_default()
                self._resume_toggle_default_selected()
            elif event.key == "enter":
                event.prevent_default()
                self._resume_execute_selected()
            elif event.key == "backspace":
                event.prevent_default()
                if self._resume_filter:
                    self._resume_filter = self._resume_filter[:-1]
                    self._refresh_resume_picker()
            elif event.character and event.character.isprintable() and len(event.character) == 1:
                event.prevent_default()
                self._resume_filter += event.character
                self._refresh_resume_picker()
            return
        if self._haul_prompt_step or self._haul_confirm_buy_station or self._dest_prompt_destination:
            return  # don't interfere with multi-step haul prompts
        if event.key not in ("up", "down"):
            return
        event.prevent_default()
        cmd_input = self.query_one("#cmd", Input)
        if not self._history:
            return
        if event.key == "up":
            if self._history_pos == len(self._history):
                # entering history: save current draft
                self._history_draft = cmd_input.value
            if self._history_pos > 0:
                self._history_pos -= 1
                cmd_input.value = self._history[self._history_pos]
                cmd_input.cursor_position = len(cmd_input.value)
        else:  # down
            if self._history_pos < len(self._history):
                self._history_pos += 1
                if self._history_pos == len(self._history):
                    cmd_input.value = self._history_draft
                else:
                    cmd_input.value = self._history[self._history_pos]
                cmd_input.cursor_position = len(cmd_input.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        event.input.value = ""

        if self._haul_prompt_step:
            self._handle_haul_prompt(raw)
            return
        if self._haul_confirm_buy_station:
            self._handle_haul_confirm_prompt(raw)
            return
        if self._dest_prompt_destination:
            destination = self._dest_prompt_destination
            parsed = self._parse_optional_nonnegative_float(
                raw,
                default=self._dest_prompt_settle_default or self._config.controls.galaxy_map_settle_seconds,
                label="Galaxy-map settle seconds",
            )
            if parsed is None:
                return
            self._dest_prompt_destination = ""
            self._dest_prompt_settle_default = None
            raw_command = self._dest_prompt_raw_command
            skip_delay = self._dest_prompt_skip_delay
            self._dest_prompt_raw_command = ""
            self._dest_prompt_skip_delay = False
            self.query_one("#cmd", Input).placeholder = _DEFAULT_COMMAND_PLACEHOLDER
            self._dispatch_dest(
                destination,
                parsed,
                skip_delay=skip_delay,
                raw_command=raw_command,
            )
            return

        if not raw:
            return

        self._dispatch_command(raw)

    def _parse_optional_nonnegative_float(self, raw: str, *, default: float, label: str) -> float | None:
        return _prompts.parse_optional_nonnegative_float(
            self,
            raw,
            default=default,
            label=label,
        )


    def on_option_list_option_highlighted(self, message: OptionList.OptionHighlighted) -> None:
        if message.option_list.id == "resume-list":
            self._update_resume_detail()

    def on_option_list_option_selected(self, message: OptionList.OptionSelected) -> None:
        if message.option_list.id == "resume-list":
            self._resume_execute_selected()


# ── Entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="ED AutoPilot Control Room — live TUI")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--market", metavar="FILTER", help="initial market filter (e.g. --market aluminium)")
    args = parser.parse_args()

    loaded = load_config_with_fallback(args.config)
    ctx = build_runtime_context(loaded.config, actions=_ALL_ROUTINE_ACTIONS)
    journal_dir = ctx.journal.effective_path

    if journal_dir is None:
        print(
            "ERROR: "
            + error_text.render(
                loaded.config,
                "journal_dir_not_found",
                source_status=ctx.journal.cli_source_status(),
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    app = ControlRoomApp(ctx, market_filter=args.market)
    previous_sigint = signal.getsignal(signal.SIGINT)

    def handle_sigint(signum, frame) -> None:  # type: ignore[no-untyped-def]
        del signum, frame
        app.request_sigint()

    signal.signal(signal.SIGINT, handle_sigint)
    try:
        app.run()
    finally:
        signal.signal(signal.SIGINT, previous_sigint)


if __name__ == "__main__":
    main()
