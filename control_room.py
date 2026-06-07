"""
ED AutoPilot Control Room

Live TUI: ship status, activity log, market tracker, and routine dispatch.

Usage:
    uv run python3 control_room.py --config config.toml
    uv run python3 control_room.py --config config.toml --market aluminium

Routine commands (type in the input bar):
    dock               dock + auto-refuel; skips supercruise-exit wait if already in normal space
    undock             launch from station
    boost              fire boost three times immediately
    escape             set speed full, then boost until Status.json says mass lock cleared
    buy <item> [N]     buy N units (default MAX) of commodity
    sell [item] [N]    sell commodity (default: market filter); amount default MAX
    jump               FSD jump sequence
    haul [commodity]   start haul loop; prompts for commodity/stations if not provided
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
import importlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from rich.markup import escape
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, OptionList, RichLog, Static
from textual.worker import get_current_worker

from edap.config import AppConfig
from edap.control_room import (
    commands as _commands,
    help as _help,
    history as _history,
    routines_haul,
    routines_movement,
    routines_nav,
    routines_station,
    routines_trade,
)
from edap.control_room.models import HaulStats, MarketData, ReplaySelection, ShipState

# Modules eligible for in-place hot reload via the `reload` command.
# Order matters: leaf modules first, then modules that import from them.
_RELOADABLE_MODULES = [
    routines_haul,
    routines_trade,
    routines_nav,
    routines_movement,
    routines_station,
    _history,
    _help,
    _commands,
]
from edap.control_room_state import (
    CommandHistoryEntry,
    ControlRoomState,
    load_control_room_state,
    save_control_room_state,
)
from edap.progress_controls import ProgressShipControls
from edap.runtime import RuntimeContext, build_runtime_context, load_config_with_fallback
from edap.ship_controls import DEFAULT_SHIP_CONTROL_ACTIONS, ShipControls
from edap.status import read_status
from edap.state import JournalWatcher, get_latest_journal_log, read_ship_state


# ── All actions needed across every supported routine ──────────────────────────

_ALL_ROUTINE_ACTIONS = list(DEFAULT_SHIP_CONTROL_ACTIONS)

_DEFAULT_COMMAND_PLACEHOLDER = "commands | help dock | replay | dock | undock | boost | escape | jump | buy <item> [N] | sell [item] | haul [commodity] | dest <system> | market ... | reload | q"


class _RoutineCancelled(Exception):
    """Raised when a control-room routine worker is cancelled."""


class _CancellationProxy:
    def __init__(self, target: Any, check_cancelled: Callable[[], None]) -> None:
        self._target = target
        self._check_cancelled = check_cancelled

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            self._check_cancelled()
            return attr(*args, **kwargs)

        return wrapped


# ── Helpers ────────────────────────────────────────────────────────────────────


def _fmt_cr(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M CR"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K CR"
    return f"{n:,} CR"


def _fuel_bar(level: float, capacity: float) -> str:
    pct = level / capacity
    filled = round(pct * 10)
    return f"{'█' * filled}{'░' * (10 - filled)}  {round(pct * 100)}%"


def _loc(item: dict[str, Any], key: str) -> str:
    return item.get(f"{key}_Localised") or item.get(key, "")


def _hhmmss() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _is_recent(ev: dict[str, Any], threshold_s: float = 120.0) -> bool:
    ts = ev.get("timestamp", "")
    if not ts:
        return True
    try:
        ev_time = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        return (datetime.utcnow() - ev_time).total_seconds() < threshold_s
    except ValueError:
        return True


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _build_log_text(msg: str) -> Text:
    line = Text.from_markup(f"[dim]{_hhmmss()}[/]  {msg}")
    line.no_wrap = False
    line.overflow = "fold"
    return line


def _read_cargo_inventory(journal_dir: Path) -> list[dict[str, Any]]:
    cargo_path = journal_dir / "Cargo.json"
    try:
        with cargo_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    inventory = data.get("Inventory", [])
    return inventory if isinstance(inventory, list) else []


def _cargo_summary_lines(inventory: list[dict[str, Any]], *, limit: int = 3) -> list[str]:
    rows = [
        item for item in inventory
        if int(item.get("Count", 0) or 0) > 0
    ]
    rows.sort(
        key=lambda item: (
            -int(item.get("Count", 0) or 0),
            str(item.get("Name_Localised") or item.get("Name") or "").lower(),
        )
    )
    result: list[str] = []
    for item in rows[:limit]:
        name = str(item.get("Name_Localised") or item.get("Name") or "?")
        count = int(item.get("Count", 0) or 0)
        result.append(f"{count}t {escape(name)}")
    return result


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

    def __init__(self, ctx: RuntimeContext, market_filter: str | None = None) -> None:
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
        self._routine_active = False
        self._active_routine_name: str | None = None
        self._verbose_controls: bool = False
        self._haul_params: dict[str, str] = {}
        self._haul_prompt_defaults: dict[str, str] = {}
        self._haul_prompt_step: str = ""  # "commodity" | "buy_station" | "sell_station" | "sell_system" | "buy_system" | "galaxy_map_settle" | "dock_timeout"
        self._haul_confirm_buy_station: str = ""
        self._dest_prompt_destination: str = ""
        self._dest_prompt_settle_default: float | None = None
        self._history: list[str] = []
        self._history_pos: int = 0  # len(_history) means "not browsing"
        self._history_draft: str = ""  # saved draft while navigating history
        self._state_path: Path = self._config.control_room.state_file
        self._saved_state = ControlRoomState()
        self._resume_entries: list[ReplaySelection] = []
        self._resume_open = False
        self._resume_filter = ""
        self._shutdown_requested: bool = False
        self._shutdown_finalized: bool = False
        self._watcher_worker: Any | None = None
        self._routine_worker: Any | None = None
        self._time_fn: Callable[[], float] = time.monotonic

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static(id="status")
                with Vertical(id="activity-pane"):
                    yield RichLog(id="activity", markup=True, highlight=True, wrap=True)
                    with Vertical(id="resume-browser"):
                        yield Static(
                            "Replay history  |  Enter execute  |  e edit  |  * set default haul  |  Esc/q close",
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
        self.query_one("#activity", RichLog).border_title = "ACTIVITY"
        self.query_one("#resume-browser", Vertical).border_title = "REPLAY HISTORY"
        self.query_one("#haul", Static).border_title = "HAUL"
        self.query_one("#market", Static).border_title = "MARKET"
        self._build_controls()
        self._load_saved_state()
        self._bootstrap_ship_state()
        self._load_market_json()
        self._refresh_status()
        self._refresh_haul_stats()
        self._refresh_market()
        self._watcher_worker = self._start_watcher()
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
        try:
            self._saved_state = load_control_room_state(self._state_path)
        except Exception as exc:
            self._saved_state = ControlRoomState()
            self._log(
                f"[yellow]Failed to load control-room state "
                f"from {escape(str(self._state_path))}: {escape(str(exc))}[/]"
            )
        self._history = [entry.raw for entry in self._saved_state.history if entry.raw]
        self._history_pos = len(self._history)

    def _save_saved_state(self) -> None:
        try:
            save_control_room_state(self._state_path, self._saved_state)
        except Exception as exc:
            self._log(
                f"[yellow]Failed to save control-room state "
                f"to {escape(str(self._state_path))}: {escape(str(exc))}[/]"
            )

    def _bootstrap_ship_state(self) -> None:
        log = get_latest_journal_log(self._journal_dir)
        if log is None:
            s0 = None
        else:
            try:
                s0 = read_ship_state(log)
                self._ship.system = s0.location
                self._ship.status = s0.status
                self._ship.ship_type = s0.ship_type
                self._ship.fuel_level = s0.fuel_level
                self._ship.fuel_capacity = s0.fuel_capacity
                self._ship.target = s0.target
            except Exception:
                s0 = None

        try:
            status = read_status(self._journal_dir)
        except Exception:
            status = None

        if status is not None:
            if status.balance is not None:
                self._ship.credits = status.balance
            if status.cargo is not None:
                self._ship.cargo_count = int(status.cargo)
        self._ship.cargo_inventory = _read_cargo_inventory(self._journal_dir)

    # ── Rendering ──────────────────────────────────────────────────────────────

    def _refresh_status(self) -> None:
        s = self._ship
        left_rows: list[str] = []
        right_rows: list[str] = []

        def left_row(label: str, value: str) -> None:
            left_rows.append(f"[dim]{label:<11}[/]  {value}")

        def right_row(label: str, value: str) -> None:
            right_rows.append(f"[dim]{label:<11}[/]  {value}")

        if s.commander:
            left_row("Commander", f"[bold]{escape(s.commander)}[/]")
        left_row("System", f"[bold]{escape(s.system or '—')}[/]")
        if s.station:
            left_row("Station", f"[bold cyan]{escape(s.station)}[/]")
        left_row("Status", escape(s.status or "—"))
        if s.fuel_level is not None and s.fuel_capacity:
            left_row("Fuel", _fuel_bar(s.fuel_level, s.fuel_capacity))
        if s.target:
            left_row("Target", f"[yellow]{escape(s.target)}[/]")

        if s.credits is not None:
            right_row("Balance", f"[green]{_fmt_cr(s.credits)}[/]")
        if s.cargo_capacity is not None:
            pct = round(s.cargo_count / s.cargo_capacity * 100) if s.cargo_capacity else 0
            right_row("Cargo", f"{s.cargo_count} / {s.cargo_capacity} t  ({pct}%)")
        elif s.cargo_count:
            right_row("Cargo", f"{s.cargo_count} t")

        cargo_lines = _cargo_summary_lines(s.cargo_inventory, limit=3)
        if cargo_lines:
            right_row("Cargo Top", cargo_lines[0])
            for line in cargo_lines[1:]:
                right_rows.append(f"{'':13}{line}")

        left_width = max((len(Text.from_markup(line).plain) for line in left_rows), default=0)
        paired_lines: list[str] = []
        row_count = max(len(left_rows), len(right_rows))
        for idx in range(row_count):
            left = left_rows[idx] if idx < len(left_rows) else ""
            right = right_rows[idx] if idx < len(right_rows) else ""
            left_plain = Text.from_markup(left).plain if left else ""
            gap = " " * max(4, left_width - len(left_plain) + 4)
            paired_lines.append(f"{left}{gap}{right}" if right else left)

        content = "\n".join(paired_lines) if paired_lines else "[dim]No data yet[/]"
        self.query_one("#status", Static).update(Text.from_markup(content))

    def _refresh_haul_stats(self) -> None:
        stats = self._haul_stats
        widget = self.query_one("#haul", Static)
        if not stats.commodity:
            lines = [
                "[dim]No haul session active.[/]",
                "",
                "Start `haul` to track cycle time,",
                "average time, and session profit.",
            ]
            if self._ship.credits is not None:
                lines.extend(["", f"[dim]Balance[/]  [green]{_fmt_cr(self._ship.credits)}[/]"])
            widget.update(Text.from_markup("\n".join(lines)))
            return

        rows: list[str] = []

        def row(label: str, value: str) -> None:
            rows.append(f"[dim]{label:<12}[/]  {value}")

        status = "active" if stats.active else "stopped"
        if stats.resumed_mid_run and not stats.clean_run_active:
            status = "resumed mid-run"
        elif stats.waiting_for_sell_departure:
            status = "waiting at sell"
        elif stats.docked_back_at_sell:
            status = "back at sell"

        current_elapsed = stats.current_run_elapsed_s
        if stats.current_run_started_at is not None and not stats.docked_back_at_sell:
            current_elapsed = self._time_fn() - stats.current_run_started_at

        avg_elapsed = (
            stats.total_run_elapsed_s / stats.completed_runs
            if stats.completed_runs > 0 else None
        )

        row("Status", escape(status))
        row("Commodity", f"[cyan]{escape(stats.commodity)}[/]")
        row("Sell", f"[bold cyan]{escape(stats.sell_station or '—')}[/]")
        row("Buy", escape(stats.buy_station or "—"))
        if self._ship.credits is not None:
            row("Balance", f"[green]{_fmt_cr(self._ship.credits)}[/]")
        row("This run", f"[green]{_fmt_cr(stats.current_run_profit)}[/]" if stats.clean_run_active else "[dim]—[/]")
        row("Elapsed", escape(_fmt_duration(current_elapsed)))
        row("Avg time", escape(_fmt_duration(avg_elapsed)))
        row("Runs", str(stats.completed_runs))
        row("Accum", f"[green]{_fmt_cr(stats.accumulated_profit)}[/]")
        row("Last run", f"[green]{_fmt_cr(stats.last_run_profit)}[/]" if stats.last_run_profit is not None else "[dim]—[/]")
        row("Last time", escape(_fmt_duration(stats.last_run_elapsed_s)))

        widget.update(Text.from_markup("\n".join(rows)))

    def _refresh_market(self) -> None:
        m = self._market
        widget = self.query_one("#market", Static)

        if not m.items:
            widget.update(Text.from_markup(
                "[dim]No market data.[/]\n\n"
                "Dock at a station and open\nthe market screen in-game."
            ))
            return

        lock_tag = "  [dim]\\[LOCKED][/]" if m.locked else ""
        header = (
            f"[bold]{escape(m.station)}[/] / {escape(m.system)}{lock_tag}\n"
            f"[dim]{escape(m.timestamp)}[/]"
        )

        term = self._market_filter.lower() if self._market_filter else None
        items = m.items
        if term:
            items = [
                i for i in items
                if term in _loc(i, "Name").lower() or term in _loc(i, "Category").lower()
            ]

        buy = [
            (_loc(i, "Name"), i.get("Stock", 0), i.get("BuyPrice", 0))
            for i in items if i.get("Stock", 0) > 0
        ]
        sell = [
            (_loc(i, "Name"), i.get("Demand", 0), i.get("SellPrice", 0))
            for i in items if i.get("DemandBracket", 0) > 0
        ]

        sections: list[str] = [header]

        if buy:
            col = max(max(len(n) for n, *_ in buy), 12)
            sections.append("\n[bold]  BUY FROM MARKET[/]")
            sections.append(f"  [dim]{'Item':<{col}}  {'Supply':>10}  {'Buy CR':>10}[/]")
            sections.append(f"  [dim]{'─' * (col + 24)}[/]")
            for name, stock, price in sorted(buy, key=lambda r: r[0].lower()):
                sections.append(f"  {escape(name):<{col}}  {stock:>10,}  {price:>8,}")

        if sell:
            col = max(max(len(n) for n, *_ in sell), 12)
            sections.append("\n[bold]  SELL TO MARKET[/]")
            sections.append(f"  [dim]{'Item':<{col}}  {'Demand':>10}  {'Sell CR':>10}[/]")
            sections.append(f"  [dim]{'─' * (col + 24)}[/]")
            for name, demand, price in sorted(sell, key=lambda r: r[0].lower()):
                sections.append(f"  {escape(name):<{col}}  {demand:>10,}  {price:>8,}")

        if not buy and not sell:
            no_match = f" matching '{escape(term)}'" if term else ""
            sections.append(f"\n[dim]No items{no_match}.[/]")

        widget.update(Text.from_markup("\n".join(sections)))

    def _log(self, msg: str) -> None:
        self.query_one("#activity", RichLog).write(_build_log_text(msg))

    def _start_haul_stats(
        self,
        *,
        commodity: str,
        buy_station: str,
        sell_station: str,
    ) -> None:
        at_sell_station = bool(
            sell_station
            and self._ship.status == "in_station"
            and self._ship.station
            and self._ship.station.lower() == sell_station.lower()
        )
        self._haul_stats = HaulStats(
            commodity=commodity,
            buy_station=buy_station,
            sell_station=sell_station,
            active=True,
            current_run_started_at=self._time_fn(),
            waiting_for_sell_departure=at_sell_station,
            resumed_mid_run=not at_sell_station,
        )
        self._refresh_haul_stats()

    def _stop_haul_stats(self) -> None:
        if not self._haul_stats.commodity:
            return
        self._haul_stats.active = False
        self._refresh_haul_stats()

    def _finalize_completed_haul_run(self) -> None:
        stats = self._haul_stats
        if not stats.clean_run_active:
            return
        elapsed = stats.current_run_elapsed_s
        if elapsed is None and stats.current_run_started_at is not None:
            elapsed = self._time_fn() - stats.current_run_started_at
        if elapsed is None:
            return
        stats.completed_runs += 1
        stats.last_run_elapsed_s = elapsed
        stats.last_run_profit = stats.current_run_profit
        stats.total_run_elapsed_s += elapsed
        stats.accumulated_profit += stats.current_run_profit
        stats.current_run_profit = 0
        stats.current_run_started_at = self._time_fn()
        stats.current_run_elapsed_s = None
        stats.docked_back_at_sell = False
        stats.waiting_for_sell_departure = False
        stats.resumed_mid_run = False

    def _handle_haul_event(self, ev: dict[str, Any], *, station_before: str | None) -> None:
        stats = self._haul_stats
        if not stats.active or not stats.commodity or not stats.sell_station:
            return

        event = ev.get("event", "")
        current_station = station_before or self._ship.station
        at_sell = bool(current_station and current_station.lower() == stats.sell_station.lower())
        at_buy = bool(stats.buy_station and current_station and current_station.lower() == stats.buy_station.lower())

        if event == "Undocked" and at_sell:
            if stats.docked_back_at_sell:
                self._finalize_completed_haul_run()
            elif stats.current_run_started_at is None:
                stats.current_run_started_at = self._time_fn()
                stats.current_run_elapsed_s = None
            stats.clean_run_active = True
            stats.waiting_for_sell_departure = False
            stats.resumed_mid_run = False
            stats.docked_back_at_sell = False
            stats.current_run_profit = 0
        elif event == "Docked" and ev.get("StationName", "").lower() == stats.sell_station.lower():
            if stats.clean_run_active and stats.current_run_started_at is not None:
                stats.current_run_elapsed_s = self._time_fn() - stats.current_run_started_at
                stats.docked_back_at_sell = True
            elif stats.resumed_mid_run:
                if stats.current_run_started_at is not None:
                    stats.current_run_elapsed_s = self._time_fn() - stats.current_run_started_at
                stats.resumed_mid_run = False
                stats.waiting_for_sell_departure = True
        elif event == "MarketBuy" and stats.clean_run_active and at_buy and "TotalCost" in ev:
            stats.current_run_profit -= int(ev["TotalCost"])
        elif event == "MarketSell" and stats.clean_run_active and at_sell and "TotalSale" in ev:
            stats.current_run_profit += int(ev["TotalSale"])

        self._refresh_haul_stats()

    def _record_history_entry(self, entry: CommandHistoryEntry) -> None:
        if self._saved_state.history and self._saved_state.history[-1].raw == entry.raw and self._saved_state.history[-1].params == entry.params:
            self._saved_state.history[-1] = entry
        else:
            self._saved_state.history.append(entry)

        limit = self._config.control_room.history_limit
        if len(self._saved_state.history) > limit:
            self._saved_state.history = self._saved_state.history[-limit:]

        self._history = [item.raw for item in self._saved_state.history if item.raw]
        self._history_pos = len(self._history)
        self._history_draft = ""
        self._save_saved_state()

    def _default_haul_matches(self, entry: CommandHistoryEntry) -> bool:
        return _history.default_haul_matches(entry, self._saved_state.default_haul)

    def _resume_label(self, entry: CommandHistoryEntry) -> str:
        return _history.resume_label(entry, self._saved_state.default_haul)

    def _filtered_resume_entries(self) -> list[ReplaySelection]:
        return _history.filtered_resume_entries(
            self._saved_state.history,
            self._saved_state.default_haul,
            self._resume_filter,
        )

    def _refresh_resume_help(self) -> None:
        filter_label = self._resume_filter or "none"
        help_text = (
            "Replay history  |  Enter execute  |  e edit  |  * set default haul  |  "
            "type prefix filter  |  Backspace delete  |  Esc/q close\n"
            f"Filter: {filter_label}"
        )
        self.query_one("#resume-help", Static).update(help_text)

    def _show_resume_picker(self) -> None:
        if not self._saved_state.history:
            self._log("[dim]No saved command history yet.[/]")
            return

        self._resume_filter = ""
        self._resume_entries = self._filtered_resume_entries()
        option_list = self.query_one("#resume-list", OptionList)
        option_list.clear_options()
        option_list.add_options([item.label for item in self._resume_entries])
        if self._resume_entries:
            option_list.highlighted = 0
        self._resume_open = True
        self.query_one("#activity", RichLog).styles.display = "none"
        self.query_one("#resume-browser", Vertical).styles.display = "block"
        self._refresh_resume_help()
        self._update_resume_detail()
        self.set_focus(option_list)

    def _refresh_resume_picker(self) -> None:
        if not self._resume_open:
            return
        option_list = self.query_one("#resume-list", OptionList)
        highlighted = option_list.highlighted or 0
        self._resume_entries = self._filtered_resume_entries()
        option_list.clear_options()
        option_list.add_options([item.label for item in self._resume_entries])
        if self._resume_entries:
            option_list.highlighted = min(highlighted, len(self._resume_entries) - 1)
        self._refresh_resume_help()
        self._update_resume_detail()

    def _close_resume_picker(self) -> None:
        self._resume_open = False
        self._resume_filter = ""
        self.query_one("#resume-browser", Vertical).styles.display = "none"
        self.query_one("#activity", RichLog).styles.display = "block"
        self.set_focus(self.query_one("#cmd", Input))

    def _selected_resume_entry(self) -> CommandHistoryEntry | None:
        if not self._resume_entries:
            return None
        option_list = self.query_one("#resume-list", OptionList)
        index = option_list.highlighted
        if index is None or index < 0 or index >= len(self._resume_entries):
            return None
        return self._resume_entries[index].entry

    def _update_resume_detail(self) -> None:
        detail = "[dim]No selection[/]"
        entry = self._selected_resume_entry()
        if entry is not None:
            detail = escape(_history.resume_detail(entry))
        self.query_one("#resume-detail", Static).update(Text.from_markup(detail))

    def _resume_execute_selected(self) -> None:
        entry = self._selected_resume_entry()
        if entry is None:
            return
        self._close_resume_picker()
        self._replay_history_entry(entry, edit=False)

    def _resume_edit_selected(self) -> None:
        entry = self._selected_resume_entry()
        if entry is None:
            return
        self._close_resume_picker()
        self._replay_history_entry(entry, edit=True)

    def _resume_toggle_default_selected(self) -> None:
        entry = self._selected_resume_entry()
        if entry is None:
            return
        if entry.command != "haul":
            self._log("[dim]Only haul entries can be saved as the default.[/]")
            return
        if self._default_haul_matches(entry):
            self._saved_state.default_haul = {}
            self._log("[dim]Cleared saved default haul.[/]")
        else:
            self._saved_state.default_haul = {str(key): str(value) for key, value in entry.params.items()}
            commodity = self._saved_state.default_haul.get("commodity", "haul")
            self._log(f"[dim]Saved default haul from history: {escape(commodity)}[/]")
        self._save_saved_state()
        self._refresh_resume_picker()

    def _replay_history_entry(self, entry: CommandHistoryEntry, *, edit: bool) -> None:
        if edit:
            if entry.command == "haul":
                self._start_haul_prompt(
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
                    self._start_dest_prompt(destination, settle_default=settle_default)
                    return
            cmd_input = self.query_one("#cmd", Input)
            cmd_input.value = entry.raw
            cmd_input.cursor_position = len(cmd_input.value)
            self.set_focus(cmd_input)
            return

        if entry.command == "haul":
            self._haul_params = {str(key): str(value) for key, value in entry.params.items()}
            self._dispatch_haul_loop()
            return
        if entry.command == "dest":
            destination = str(entry.params.get("destination", "")).strip()
            if destination:
                settle_value = entry.params.get("galaxy_map_settle")
                settle = float(settle_value) if settle_value is not None else self._config.controls.galaxy_map_settle_seconds
                self._dispatch_dest(destination, settle)
            return

        self._dispatch_command(entry.raw)

    # ── Market JSON ────────────────────────────────────────────────────────────

    def _load_market_json(self) -> None:
        if self._market.locked or not self._market_path.exists():
            return
        mtime = self._market_path.stat().st_mtime
        if mtime == self._market_mtime:
            return
        self._market_mtime = mtime
        try:
            with self._market_path.open() as fh:
                data = json.load(fh)
            self._market = MarketData(
                station=data.get("StationName", "?"),
                system=data.get("StarSystem", "?"),
                timestamp=data.get("timestamp", ""),
                items=data.get("Items", []),
                locked=self._market.locked,
            )
            self._refresh_market()
        except Exception:
            pass

    # ── Journal event processing ───────────────────────────────────────────────

    def _handle_event(self, ev: dict[str, Any]) -> None:
        event = ev.get("event", "")
        s = self._ship
        station_before = s.station

        if event == "Commander":
            s.commander = ev.get("Name", s.commander)
        elif event == "LoadGame":
            s.commander = ev.get("Commander", s.commander)
            s.ship_type = ev.get("Ship", s.ship_type)
            if "Credits" in ev:
                s.credits = ev["Credits"]
        elif event == "Loadout":
            s.ship_type = ev.get("Ship", s.ship_type)
            s.cargo_capacity = ev.get("CargoCapacity", s.cargo_capacity)

        if event in {"Location", "FSDJump"} and "StarSystem" in ev:
            s.system = ev["StarSystem"]
        if event == "Docked" or (
            event in {"Location", "CarrierJump"} and ev.get("Docked") is True
        ):
            s.station = ev.get("StationName", s.station)
            s.system = ev.get("StarSystem", s.system)
        if event in {"Undocked", "SupercruiseExit"} or (
            event in {"Location", "CarrierJump"} and ev.get("Docked") is False
        ):
            s.station = None

        if event == "StartJump":
            s.status = f"starting_{ev.get('JumpType', '').lower()}"
        elif event in {"SupercruiseEntry", "FSDJump"}:
            s.status = "in_supercruise"
        elif event in {"SupercruiseExit", "DockingCancelled", "Undocked"} or (
            event in {"Location", "CarrierJump"} and ev.get("Docked") is False
        ):
            s.status = "in_space"
        elif event == "DockingRequested":
            s.status = "starting_docking"
        elif event == "Docked" or (
            event in {"Location", "CarrierJump"} and ev.get("Docked") is True
        ):
            s.status = "in_station"

        if "FuelLevel" in ev and s.ship_type != "TestBuggy":
            s.fuel_level = ev["FuelLevel"]
        if "FuelCapacity" in ev and s.ship_type != "TestBuggy":
            fc = ev["FuelCapacity"]
            s.fuel_capacity = fc.get("Main") if isinstance(fc, dict) else fc
        if event == "FuelScoop" and "Total" in ev:
            s.fuel_level = ev["Total"]

        if event == "MarketBuy" and s.credits is not None and "TotalCost" in ev:
            s.credits -= ev["TotalCost"]
        elif event == "MarketSell" and s.credits is not None and "TotalSale" in ev:
            s.credits += ev["TotalSale"]
        elif "Credits" in ev and event not in {"MarketBuy", "MarketSell"}:
            s.credits = ev["Credits"]

        if event == "Cargo" and "Count" in ev:
            s.cargo_count = ev["Count"]
            if "Inventory" in ev:
                s.cargo_inventory = list(ev["Inventory"])
        elif event == "MarketBuy" and "Count" in ev:
            s.cargo_count += ev["Count"]
        elif event == "MarketSell" and "Count" in ev:
            s.cargo_count = max(0, s.cargo_count - ev["Count"])

        if event == "FSDTarget":
            s.target = ev.get("Name") if ev.get("Name") != s.system else None
        elif event == "FSDJump" and s.system == s.target:
            s.target = None

        msg = self._activity_line(ev)
        if msg:
            self._log(msg)

        if event == "Docked":
            self._load_market_json()

        self._refresh_status()
        self._handle_haul_event(ev, station_before=station_before)

    def _activity_line(self, ev: dict[str, Any]) -> str | None:
        if not _is_recent(ev):
            return None
        event = ev.get("event", "")
        if event == "FSDJump":
            return f"Jumped to [bold]{escape(ev.get('StarSystem', '?'))}[/]"
        if event == "StartJump" and ev.get("JumpType") == "Hyperspace":
            return f"Jumping to [bold]{escape(ev.get('StarSystem', '?'))}[/]"
        if event == "SupercruiseEntry":
            return "Entered supercruise"
        if event == "SupercruiseExit":
            body = ev.get("Body", "")
            return f"Exited supercruise{f' near {escape(body)}' if body else ''}"
        if event == "Docked":
            return f"Docked at [bold cyan]{escape(ev.get('StationName', '?'))}[/]"
        if event == "Undocked":
            return f"Undocked from {escape(ev.get('StationName', '?'))}"
        if event == "DockingGranted":
            return "[dim]Docking granted[/]"
        if event == "DockingDenied":
            reason = ev.get("Reason", "")
            return f"[yellow]Docking denied[/]{f': {escape(reason)}' if reason else ''}"
        if event == "DockingCancelled":
            return "[dim]Docking cancelled[/]"
        if event == "MarketBuy":
            name = escape(ev.get("Type_Localised") or ev.get("Type", "?"))
            return f"Bought [cyan]{ev.get('Count')}t {name}[/]  [dim]{_fmt_cr(ev.get('TotalCost', 0))}[/]"
        if event == "MarketSell":
            name = escape(ev.get("Type_Localised") or ev.get("Type", "?"))
            return f"Sold [cyan]{ev.get('Count')}t {name}[/]  →  [green]{_fmt_cr(ev.get('TotalSale', 0))}[/]"
        if event == "Refuelled":
            return f"Refuelled {ev.get('Amount', 0):.1f}t"
        if event == "MissionCompleted":
            label = escape(ev.get("LocalisedName") or ev.get("Name", "mission"))
            return f"Mission: {label}  →  [green]{_fmt_cr(ev.get('Reward', 0))}[/]"
        return None

    # ── Background status watcher ──────────────────────────────────────────────

    @work(thread=True, group="watchers", exclusive=True)
    def _start_watcher(self) -> None:
        worker = get_current_worker()
        watcher = JournalWatcher(self._journal_dir)
        last_market_check = 0.0
        while not worker.is_cancelled:
            try:
                for ev in watcher.poll():
                    self.call_from_thread(self._handle_event, ev)
                now = time.monotonic()
                if now - last_market_check > 2.0:
                    self.call_from_thread(self._load_market_json)
                    self.call_from_thread(self._refresh_haul_stats)
                    last_market_check = now
            except Exception:
                time.sleep(1.0)

    # ── Routine dispatch ───────────────────────────────────────────────────────

    def _check_routine_ready(self) -> bool:
        if self._controls is None:
            self._log("[red]Controls unavailable — check bindings config[/]")
            return False
        if self._routine_active:
            self._log("[yellow]A routine is already running — wait for it to finish[/]")
            return False
        return True

    def _make_progress(self) -> Callable[[str], None]:
        def progress(msg: str) -> None:
            self._raise_if_worker_cancelled()
            self.call_from_thread(self._log, f"[dim]  {escape(msg)}[/]")
        return progress

    def _make_controls(self, progress_fn: Callable[[str], None]) -> ProgressShipControls:
        controls = ProgressShipControls(self._controls, progress_fn, verbose=self._verbose_controls)  # type: ignore[arg-type]
        return _CancellationProxy(controls, self._raise_if_worker_cancelled)

    def _make_watcher(self) -> Any:
        watcher = JournalWatcher(self._journal_dir)
        return _CancellationProxy(watcher, self._raise_if_worker_cancelled)

    def _make_sleeper(self) -> Callable[[float], None]:
        def sleeper(delay_s: float) -> None:
            deadline = time.monotonic() + max(0.0, delay_s)
            while True:
                self._raise_if_worker_cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                time.sleep(min(0.1, remaining))
        return sleeper

    def _raise_if_worker_cancelled(self) -> None:
        worker = get_current_worker()
        if worker.is_cancelled:
            raise _RoutineCancelled()

    @work(thread=True, group="routines", exclusive=True)
    def _run_in_thread(self, fn: Callable[[], RoutineResult | None]) -> None:
        worker = get_current_worker()
        try:
            result = fn()
            if worker.is_cancelled:
                self.call_from_thread(self._log, "[yellow]Routine cancelled.[/]")
            elif result is not None:
                status = result.dispatch.status
                color = "green" if status == "ok" else "yellow"
                self.call_from_thread(
                    self._log, f"[{color}]Done: {escape(result.action)} ({escape(status)})[/]"
                )
        except _RoutineCancelled:
            self.call_from_thread(self._log, "[yellow]Routine cancelled.[/]")
        except Exception as exc:
            self.call_from_thread(self._log, f"[red]Routine error: {escape(str(exc))}[/]")
        finally:
            self.call_from_thread(self._clear_routine)

    def _clear_routine(self) -> None:
        self._routine_active = False
        self._routine_worker = None
        if self._active_routine_name == "haul":
            self._stop_haul_stats()
        self._active_routine_name = None
        if self._shutdown_requested:
            self._finalize_shutdown()

    # ── Routine commands ───────────────────────────────────────────────────────

    def _cmd_dock(self) -> None:
        routines_station.cmd_dock(self)

    def _cmd_undock(self) -> None:
        routines_station.cmd_undock(self)

    def _cmd_jump(self) -> None:
        routines_movement.cmd_jump(self)

    def _cmd_escape(self) -> None:
        routines_movement.cmd_escape(self)

    def _cmd_boost(self) -> None:
        routines_movement.cmd_boost(self)

    def _start_dest_prompt(self, destination: str, *, settle_default: float | None = None) -> None:
        self._dest_prompt_destination = destination
        self._dest_prompt_settle_default = settle_default if settle_default is not None else self._config.controls.galaxy_map_settle_seconds
        default_settle = self._dest_prompt_settle_default
        self._log(f"Destination: [bold]{escape(destination)}[/]")
        self._log(
            f"[dim]Galaxy-map settle seconds? "
            f"(Enter = {default_settle:.1f})[/]"
        )
        self.query_one("#cmd", Input).placeholder = (
            f"galaxy map settle seconds (Enter = {default_settle:.1f})..."
        )

    def _cmd_dest(self, destination: str) -> None:
        routines_nav.cmd_dest(self, destination)

    def _dispatch_dest(self, destination: str, galaxy_map_settle: float) -> None:
        routines_nav.dispatch_dest(self, destination, galaxy_map_settle)

    def _saved_haul_defaults(self, seed: dict[str, str] | None = None) -> dict[str, str]:
        defaults = dict(self._saved_state.default_haul)
        if seed:
            defaults.update({key: value for key, value in seed.items() if value != ""})
        if not defaults.get("sell_station") and self._ship.station:
            defaults["sell_station"] = self._ship.station
        if not defaults.get("sell_system") and self._ship.system:
            defaults["sell_system"] = self._ship.system
        if not defaults.get("galaxy_map_settle"):
            defaults["galaxy_map_settle"] = str(self._config.controls.galaxy_map_settle_seconds)
        if not defaults.get("dock_timeout"):
            defaults["dock_timeout"] = str(self._config.controls.haul_dock_timeout_seconds)
        return defaults

    def _start_haul_prompt(
        self,
        *,
        commodity: str,
        prompt_for_commodity: bool,
        seed: dict[str, str] | None = None,
    ) -> None:
        self._haul_params = {
            "commodity": commodity.strip(),
            "buy_station": "",
            "sell_station": "",
            "sell_system": "",
            "buy_system": "",
            "galaxy_map_settle": "",
            "dock_timeout": "",
        }
        self._haul_prompt_defaults = self._saved_haul_defaults(seed)
        self._log("Haul loop setup — enter parameters below:")
        if prompt_for_commodity:
            self._haul_prompt_step = "commodity"
            default_commodity = self._haul_prompt_defaults.get("commodity", "")
            if default_commodity:
                self._log(f"[dim]Commodity to buy? (Enter = {escape(default_commodity)})[/]")
                self.query_one("#cmd", Input).placeholder = f"commodity (Enter = {default_commodity})..."
            else:
                self._log("[dim]Commodity to buy? (e.g. Aluminium)[/]")
                self.query_one("#cmd", Input).placeholder = "commodity..."
            return

        self._log(f"Haul loop: commodity = [cyan]{escape(self._haul_params['commodity'])}[/]")
        self._haul_prompt_step = "buy_station"
        default_buy_station = self._haul_prompt_defaults.get("buy_station", "")
        if default_buy_station:
            self._log(f"[dim]Buy station name? (Enter = {escape(default_buy_station)})[/]")
            self.query_one("#cmd", Input).placeholder = f"buy station (Enter = {default_buy_station})..."
        else:
            self._log("[dim]Buy station name? (press Enter to skip)[/]")
            self.query_one("#cmd", Input).placeholder = "buy station (Enter to skip)..."

    def _cmd_buy(self, rest: str) -> None:
        routines_trade.cmd_buy(self, rest)

    def _cmd_sell(self, rest: str) -> None:
        routines_trade.cmd_sell(self, rest)

    def _sell_item(self, target: str, amount: int | str) -> None:
        routines_trade.sell_item(self, target, amount)

    def _sell_all(self) -> None:
        routines_trade.sell_all(self)

    def _cmd_haul(self, rest: str) -> None:
        routines_haul.cmd_haul(self, rest)

    def _start_haul_confirm_prompt(self, station: str) -> None:
        self._haul_confirm_buy_station = station
        self._log(
            f"[dim]Assume current station [cyan]{escape(station)}[/] is the buy station? "
            f"(Enter = yes, no to cancel)[/]"
        )
        self.query_one("#cmd", Input).placeholder = "confirm buy station? Enter = yes, no to cancel..."

    def _handle_haul_confirm_prompt(self, value: str) -> None:
        answer = value.strip().lower()
        if answer in {"", "y", "yes"}:
            station = self._haul_confirm_buy_station
            self._haul_confirm_buy_station = ""
            self._haul_params["buy_station"] = station
            self._log(f"  Buy station confirmed: [cyan]{escape(station)}[/]")
            self.query_one("#cmd", Input).placeholder = _DEFAULT_COMMAND_PLACEHOLDER
            self._dispatch_haul_loop()
            return
        if answer in {"n", "no"}:
            station = self._haul_confirm_buy_station
            self._haul_confirm_buy_station = ""
            self._log(
                f"[yellow]Haul launch cancelled — buy station left unresolved "
                f"for [cyan]{escape(station)}[/].[/]"
            )
            self.query_one("#cmd", Input).placeholder = _DEFAULT_COMMAND_PLACEHOLDER
            return
        self._log("[red]Press Enter for yes, or type no to cancel.[/]")

    def _handle_haul_prompt(self, value: str) -> None:
        if self._haul_prompt_step == "commodity":
            resolved = value.strip() or self._haul_prompt_defaults.get("commodity", "")
            if not resolved:
                self._log("[red]Commodity is required — enter a commodity name.[/]")
                return
            self._haul_params["commodity"] = resolved
            self._log(f"  Commodity: [cyan]{escape(resolved)}[/]")
            self._haul_prompt_step = "buy_station"
            default_buy_station = self._haul_prompt_defaults.get("buy_station", "")
            if default_buy_station:
                self._log(f"[dim]Buy station name? (Enter = {escape(default_buy_station)})[/]")
                self.query_one("#cmd", Input).placeholder = f"buy station (Enter = {default_buy_station})..."
            else:
                self._log("[dim]Buy station name? (press Enter to skip)[/]")
                self.query_one("#cmd", Input).placeholder = "buy station (Enter to skip)..."
        elif self._haul_prompt_step == "buy_station":
            resolved = value.strip() or self._haul_prompt_defaults.get("buy_station", "")
            self._haul_params["buy_station"] = resolved
            if resolved:
                self._log(f"  Buy station: [cyan]{escape(resolved)}[/]")
            else:
                self._log("  Buy station: [dim](none)[/]")
            self._haul_prompt_step = "sell_station"
            default_sell_station = self._haul_prompt_defaults.get("sell_station", "")
            if default_sell_station:
                self._log(f"[dim]Sell station name? (Enter = {escape(default_sell_station)})[/]")
                self.query_one("#cmd", Input).placeholder = f"sell station (Enter = {default_sell_station})..."
            else:
                current = self._ship.station or "current station"
                self._log(f"[dim]Sell station name? (Enter to use {escape(current)})[/]")
                self.query_one("#cmd", Input).placeholder = f"sell station (Enter = {current})..."
        elif self._haul_prompt_step == "sell_station":
            resolved = value.strip() or self._haul_prompt_defaults.get("sell_station", "")
            self._haul_params["sell_station"] = resolved
            if resolved:
                self._log(f"  Sell station: [cyan]{escape(resolved)}[/]")
            else:
                self._log(f"  Sell station: [dim](current station)[/]")
            self._haul_prompt_step = "sell_system"
            default_sell_system = self._haul_prompt_defaults.get("sell_system", "")
            if default_sell_system:
                self._log(f"[dim]Sell system? (Enter = {escape(default_sell_system)})[/]")
                self.query_one("#cmd", Input).placeholder = f"sell system (Enter = {default_sell_system})..."
            else:
                current_system = self._ship.system or "current system"
                self._log(f"[dim]Sell system? (Enter to use {escape(current_system)})[/]")
                self.query_one("#cmd", Input).placeholder = f"sell system (Enter = {current_system})..."
        elif self._haul_prompt_step == "sell_system":
            resolved = value.strip() or self._haul_prompt_defaults.get("sell_system", "")
            self._haul_params["sell_system"] = resolved
            if resolved:
                self._log(f"  Sell system: [cyan]{escape(resolved)}[/]")
            else:
                self._log(f"  Sell system: [dim](current system)[/]")
            self._haul_prompt_step = "buy_system"
            default_buy_system = self._haul_prompt_defaults.get("buy_system", "")
            if default_buy_system:
                self._log(f"[dim]Buy system? (Enter = {escape(default_buy_system)})[/]")
                self.query_one("#cmd", Input).placeholder = f"buy system (Enter = {default_buy_system})..."
            else:
                self._log("[dim]Buy system? (press Enter to skip)[/]")
                self.query_one("#cmd", Input).placeholder = "buy system (Enter to skip)..."
        elif self._haul_prompt_step == "buy_system":
            resolved = value.strip() or self._haul_prompt_defaults.get("buy_system", "")
            self._haul_params["buy_system"] = resolved
            if resolved:
                self._log(f"  Buy system: [cyan]{escape(resolved)}[/]")
            else:
                self._log("  Buy system: [dim](none)[/]")
            default_settle = float(self._haul_prompt_defaults.get("galaxy_map_settle", self._config.controls.galaxy_map_settle_seconds))
            self._haul_prompt_step = "galaxy_map_settle"
            self._log(
                f"[dim]Galaxy-map settle seconds? "
                f"(Enter = {default_settle:.1f})[/]"
            )
            self.query_one("#cmd", Input).placeholder = (
                f"galaxy map settle seconds (Enter = {default_settle:.1f})..."
            )
        elif self._haul_prompt_step == "galaxy_map_settle":
            parsed = self._parse_optional_nonnegative_float(
                value,
                default=float(self._haul_prompt_defaults.get("galaxy_map_settle", self._config.controls.galaxy_map_settle_seconds)),
                label="Galaxy-map settle seconds",
            )
            if parsed is None:
                return
            self._haul_params["galaxy_map_settle"] = str(parsed)
            self._log(f"  Galaxy-map settle: [cyan]{parsed:.1f}s[/]")
            default_timeout = float(self._haul_prompt_defaults.get("dock_timeout", self._config.controls.haul_dock_timeout_seconds))
            self._haul_prompt_step = "dock_timeout"
            self._log(
                f"[dim]Haul docking timeout seconds? "
                f"(Enter = {default_timeout:.1f})[/]"
            )
            self.query_one("#cmd", Input).placeholder = (
                f"haul docking timeout seconds (Enter = {default_timeout:.1f})..."
            )
        elif self._haul_prompt_step == "dock_timeout":
            parsed = self._parse_optional_nonnegative_float(
                value,
                default=float(self._haul_prompt_defaults.get("dock_timeout", self._config.controls.haul_dock_timeout_seconds)),
                label="Haul docking timeout seconds",
            )
            if parsed is None:
                return
            self._haul_params["dock_timeout"] = str(parsed)
            self._log(f"  Haul docking timeout: [cyan]{parsed:.1f}s[/]")
            self._haul_prompt_step = ""
            self._haul_prompt_defaults = {}
            self.query_one("#cmd", Input).placeholder = _DEFAULT_COMMAND_PLACEHOLDER
            self._dispatch_haul_loop()

    def _dispatch_haul_loop(self) -> None:
        routines_haul.dispatch_haul_loop(self)

    # ── Hot reload ─────────────────────────────────────────────────────────────

    def _cmd_reload(self) -> None:
        reloaded: list[str] = []
        for module in _RELOADABLE_MODULES:
            try:
                importlib.reload(module)
                reloaded.append(module.__name__)
            except Exception as exc:
                self._log(f"[red]Reload failed for {escape(module.__name__)}: {escape(str(exc))}[/]")
                return
        self._log("[green]Hot-reloaded modules:[/]")
        for name in reloaded:
            self._log(f"  [dim]•[/] {escape(name)}")
        self._log("[dim]Next command dispatch will use the new code. App/widget edits still need a restart.[/]")

    # ── Quit ───────────────────────────────────────────────────────────────────

    def action_request_quit(self) -> None:
        if self._routine_active and self._routine_worker is not None:
            self._cancel_active_routine("Ctrl-C / Ctrl-D")
            return
        self._request_shutdown("Ctrl-C / Ctrl-D")

    def _cancel_active_routine(self, source: str) -> None:
        self._log(f"[yellow]{escape(source)} received — cancelling active routine.[/]")
        self._routine_worker.cancel()

    def _request_shutdown(self, source: str) -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        self._log(f"[yellow]{escape(source)} received — exiting control room.[/]")
        self._finalize_shutdown()

    def _finalize_shutdown(self) -> None:
        if self._shutdown_finalized:
            return
        self._shutdown_finalized = True
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
            self.query_one("#cmd", Input).placeholder = _DEFAULT_COMMAND_PLACEHOLDER
            self._dispatch_dest(destination, parsed)
            return

        if not raw:
            return

        self._dispatch_command(raw)

    def _dispatch_command(self, raw: str) -> None:
        _commands.dispatch(self, raw)

    def _parse_optional_nonnegative_float(self, raw: str, *, default: float, label: str) -> float | None:
        value = raw.strip()
        if not value:
            return default
        try:
            parsed = float(value)
        except ValueError:
            self._log(f"[red]{escape(label)} must be a number.[/]")
            return None
        if parsed < 0:
            self._log(f"[red]{escape(label)} must be non-negative.[/]")
            return None
        return parsed


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
            "ERROR: journal directory not found "
            f"(source: {ctx.journal.cli_source_status()}). "
            "Set paths.journal_dir in config.toml.",
            file=sys.stderr,
        )
        sys.exit(1)

    ControlRoomApp(ctx, market_filter=args.market).run()


if __name__ == "__main__":
    main()
