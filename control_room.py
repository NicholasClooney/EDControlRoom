"""
ED AutoPilot Control Room

Live TUI: ship status, activity log, market tracker, and routine dispatch.

Usage:
    uv run python3 control_room.py --config config.toml
    uv run python3 control_room.py --config config.toml --market aluminium

Routine commands (type in the input bar):
    dock               dock + auto-refuel; skips supercruise-exit wait if already in normal space
    undock             launch from station
    buy <item> [N]     buy N units (default MAX) of commodity
    sell [item] [N]    sell commodity (default: market filter); amount default MAX
    jump               FSD jump sequence
    haul [commodity]   start haul loop; prompts for commodity/stations if not provided

Market commands:
    market [filter]    filter market panel
    market lock        freeze panel to current station
    market unlock      unfreeze panel

Other:
    q / quit           exit
    help               show this list
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from rich.markup import escape
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static
from textual.worker import get_current_worker

from edap.config import AppConfig
from edap.progress_controls import ProgressShipControls
from edap.routines import dock, haul_loop, jump, market_buy, market_sell, undock, RoutineResult
from edap.runtime import RuntimeContext, build_runtime_context, load_config_with_fallback
from edap.ship_controls import ShipControls
from edap.state import JournalWatcher, get_latest_journal_log, read_ship_state


# ── All actions needed across every supported routine ──────────────────────────

_ALL_ROUTINE_ACTIONS = [
    "SetSpeedZero", "HyperSuperCombination",
    "BoostButton", "FocusLeftPanel",
    "UI_Back", "UI_Up", "UI_Down", "UI_Select", "UI_Left", "UI_Right",
    "CycleNextPanel", "CyclePreviousPanel",
    "HeadLookReset",
]


# ── State ──────────────────────────────────────────────────────────────────────


@dataclass
class _ShipState:
    commander: str | None = None
    ship_type: str | None = None
    system: str | None = None
    station: str | None = None
    status: str | None = None
    fuel_level: float | None = None
    fuel_capacity: float | None = None
    credits: int | None = None
    cargo_count: int = 0
    cargo_capacity: int | None = None
    cargo_inventory: list[dict[str, Any]] = field(default_factory=list)
    target: str | None = None


@dataclass
class _MarketData:
    station: str = ""
    system: str = ""
    timestamp: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)
    locked: bool = False


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


def _parse_amount(s: str) -> int | str | None:
    if s.upper() == "MAX":
        return "MAX"
    try:
        n = int(s)
        return n if n > 0 else None
    except ValueError:
        return None


# ── App ────────────────────────────────────────────────────────────────────────


class ControlRoomApp(App[None]):
    CSS = """
    Screen  { layout: vertical; }
    #main   { height: 1fr; }
    #left   { width: 45%; }
    #status {
        height: auto;
        max-height: 14;
        border: solid $primary;
        padding: 0 1;
    }
    #activity {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    #market {
        width: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    #cmd { height: 3; }
    """

    def __init__(self, ctx: RuntimeContext, market_filter: str | None = None) -> None:
        super().__init__()
        self._ctx = ctx
        self._config: AppConfig = ctx.config
        self._journal_dir: Path = ctx.journal.effective_path  # type: ignore[assignment]
        self._market_path = self._journal_dir / "Market.json"
        self._ship = _ShipState()
        self._market = _MarketData()
        self._market_filter = market_filter
        self._market_mtime: float | None = None
        self._controls: ShipControls | None = None
        self._routine_active = False
        self._verbose_controls: bool = False
        self._haul_params: dict[str, str] = {}
        self._haul_prompt_step: str = ""  # "commodity" | "buy_station" | "sell_station" | ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static(id="status")
                yield RichLog(id="activity", markup=True, highlight=True, wrap=True)
            yield Static(id="market")
        yield Input(placeholder="dock | undock | buy <item> [N] | sell [item] | haul [commodity] | market [filter|lock|unlock] | q", id="cmd")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "ED Control Room"
        self.query_one("#status", Static).border_title = "SHIP STATUS"
        self.query_one("#activity", RichLog).border_title = "ACTIVITY"
        self.query_one("#market", Static).border_title = "MARKET"
        self._build_controls()
        self._bootstrap_ship_state()
        self._load_market_json()
        self._refresh_status()
        self._refresh_market()
        self._start_watcher()

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

    def _bootstrap_ship_state(self) -> None:
        log = get_latest_journal_log(self._journal_dir)
        if log is None:
            return
        try:
            s0 = read_ship_state(log)
            self._ship.system = s0.location
            self._ship.status = s0.status
            self._ship.ship_type = s0.ship_type
            self._ship.fuel_level = s0.fuel_level
            self._ship.fuel_capacity = s0.fuel_capacity
            self._ship.target = s0.target
        except Exception:
            pass

    # ── Rendering ──────────────────────────────────────────────────────────────

    def _refresh_status(self) -> None:
        s = self._ship
        rows: list[str] = []

        def row(label: str, value: str) -> None:
            rows.append(f"[dim]{label:<11}[/]  {value}")

        if s.commander:
            row("Commander", f"[bold]{escape(s.commander)}[/]")
        row("System", f"[bold]{escape(s.system or '—')}[/]")
        if s.station:
            row("Station", f"[bold cyan]{escape(s.station)}[/]")
        row("Status", escape(s.status or "—"))
        if s.fuel_level is not None and s.fuel_capacity:
            row("Fuel", _fuel_bar(s.fuel_level, s.fuel_capacity))
        if s.credits is not None:
            row("Credits", f"[green]{_fmt_cr(s.credits)}[/]")
        if s.cargo_capacity is not None:
            pct = round(s.cargo_count / s.cargo_capacity * 100) if s.cargo_capacity else 0
            row("Cargo", f"{s.cargo_count} / {s.cargo_capacity} t  ({pct}%)")
        elif s.cargo_count:
            row("Cargo", f"{s.cargo_count} t")
        if s.target:
            row("Target", f"[yellow]{escape(s.target)}[/]")

        content = "\n".join(rows) if rows else "[dim]No data yet[/]"
        self.query_one("#status", Static).update(Text.from_markup(content))

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
        self.query_one("#activity", RichLog).write(
            f"[dim]{_hhmmss()}[/]  {msg}"
        )

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
            self._market = _MarketData(
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
        if event == "Docked":
            s.station = ev.get("StationName")
            s.system = ev.get("StarSystem", s.system)
        if event in {"Undocked", "SupercruiseExit"}:
            s.station = None

        if event == "StartJump":
            s.status = f"starting_{ev.get('JumpType', '').lower()}"
        elif event in {"SupercruiseEntry", "FSDJump"}:
            s.status = "in_supercruise"
        elif event in {"SupercruiseExit", "DockingCancelled", "Undocked"}:
            s.status = "in_space"
        elif event == "DockingRequested":
            s.status = "starting_docking"
        elif event == "Docked":
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

    @work(thread=True)
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
            self.call_from_thread(self._log, f"[dim]  {escape(msg)}[/]")
        return progress

    def _make_controls(self, progress_fn: Callable[[str], None]) -> ProgressShipControls:
        return ProgressShipControls(self._controls, progress_fn, verbose=self._verbose_controls)  # type: ignore[arg-type]

    @work(thread=True)
    def _run_in_thread(self, fn: Callable[[], RoutineResult | None]) -> None:
        try:
            result = fn()
            if result is not None:
                status = result.dispatch.status
                color = "green" if status == "ok" else "yellow"
                self.call_from_thread(
                    self._log, f"[{color}]Done: {escape(result.action)} ({escape(status)})[/]"
                )
        except Exception as exc:
            self.call_from_thread(self._log, f"[red]Routine error: {escape(str(exc))}[/]")
        finally:
            self.call_from_thread(self._clear_routine)

    def _clear_routine(self) -> None:
        self._routine_active = False

    # ── Routine commands ───────────────────────────────────────────────────────

    def _cmd_dock(self) -> None:
        if not self._check_routine_ready():
            return
        skip_scx = self._ship.status == "in_space"
        progress = self._make_progress()
        controls = self._make_controls(progress)
        step_delay = self._config.controls.step_delay_seconds
        watcher = JournalWatcher(self._journal_dir)

        self._routine_active = True
        label = "dock (already in space)" if skip_scx else "dock (waiting for supercruise exit)"
        self._log(f"Starting {label}, auto-refuel on...")
        self._run_in_thread(lambda: dock(
            controls,
            watcher,
            wait_for_supercruise_exit=not skip_scx,
            auto_refuel=True,
            step_delay_s=step_delay,
            progress_fn=progress,
        ))

    def _cmd_undock(self) -> None:
        if not self._check_routine_ready():
            return
        progress = self._make_progress()
        controls = self._make_controls(progress)
        step_delay = self._config.controls.step_delay_seconds
        watcher = JournalWatcher(self._journal_dir)

        self._routine_active = True
        self._log("Starting undock...")
        self._run_in_thread(lambda: undock(
            controls,
            watcher,
            step_delay_s=step_delay,
            progress_fn=progress,
        ))

    def _cmd_jump(self) -> None:
        if not self._check_routine_ready():
            return
        progress = self._make_progress()
        controls = self._make_controls(progress)
        watcher = JournalWatcher(self._journal_dir)

        self._routine_active = True
        self._log("Starting jump sequence...")
        self._run_in_thread(lambda: jump(
            controls,
            watcher,
            progress_fn=progress,
        ))

    def _cmd_buy(self, rest: str) -> None:
        if not self._check_routine_ready():
            return
        parts = rest.split(None, 1)
        if not parts:
            self._log("[red]Usage: buy <item> [amount|max][/]")
            return
        target = parts[0]
        amount = _parse_amount(parts[1].strip() if len(parts) > 1 else "MAX")
        if amount is None:
            self._log(f"[red]Invalid amount — use a positive integer or MAX[/]")
            return

        progress = self._make_progress()
        controls = self._make_controls(progress)
        step_delay = self._config.controls.step_delay_seconds
        market_path = self._market_path
        watcher = JournalWatcher(self._journal_dir)

        self._routine_active = True
        amt_label = str(amount) + ("t" if isinstance(amount, int) else "")
        self._log(f"Buying {amt_label} [cyan]{escape(target)}[/]...")
        self._run_in_thread(lambda: market_buy(
            controls,
            watcher,
            market_path=market_path,
            target=target,
            amount=amount,
            step_delay_s=step_delay,
            progress_fn=progress,
        ))

    def _cmd_sell(self, rest: str) -> None:
        if not self._check_routine_ready():
            return
        if rest:
            parts = rest.split(None, 1)
            target = parts[0]
            amount = _parse_amount(parts[1].strip() if len(parts) > 1 else "MAX")
            if amount is None:
                self._log("[red]Invalid amount — use a positive integer or MAX[/]")
                return
            self._sell_item(target, amount)
        else:
            self._sell_all()

    def _sell_item(self, target: str, amount: int | str) -> None:
        progress = self._make_progress()
        controls = self._make_controls(progress)
        step_delay = self._config.controls.step_delay_seconds
        market_path = self._market_path
        watcher = JournalWatcher(self._journal_dir)

        self._routine_active = True
        amt_label = str(amount) + ("t" if isinstance(amount, int) else "")
        self._log(f"Selling {amt_label} [cyan]{escape(target)}[/]...")
        self._run_in_thread(lambda: market_sell(
            controls, watcher,
            market_path=market_path,
            target=target,
            amount=amount,
            step_delay_s=step_delay,
            progress_fn=progress,
        ))

    def _sell_all(self) -> None:
        # Build a sellable snapshot from cargo: skip mission cargo and stolen items.
        inventory = [
            item for item in self._ship.cargo_inventory
            if item.get("Count", 0) > 0
            and item.get("Stolen", 0) == 0
            and "MissionID" not in item
        ]
        if not inventory:
            self._log("[yellow]Nothing sellable in cargo (empty, all stolen, or all mission cargo)[/]")
            return

        progress = self._make_progress()
        controls = self._make_controls(progress)
        step_delay = self._config.controls.step_delay_seconds
        market_path = self._market_path
        watcher = JournalWatcher(self._journal_dir)

        names = ", ".join(item.get("Name_Localised") or item.get("Name", "?") for item in inventory)
        self._log(f"Selling all cargo: [cyan]{escape(names)}[/]")
        self._routine_active = True

        def run_all() -> None:
            for item in inventory:
                name = item.get("Name_Localised") or item.get("Name", "?")
                self.call_from_thread(self._log, f"  → [cyan]{escape(name)}[/] (MAX)...")
                try:
                    result = market_sell(
                        controls, watcher,
                        market_path=market_path,
                        target=name,
                        amount="MAX",
                        step_delay_s=step_delay,
                        progress_fn=progress,
                    )
                    status = result.dispatch.status
                    color = "green" if status == "ok" else "yellow"
                    self.call_from_thread(self._log, f"  [{color}]{escape(name)}: {escape(status)}[/]")
                except Exception as exc:
                    self.call_from_thread(
                        self._log, f"  [yellow]Skipped {escape(name)}: {escape(str(exc))}[/]"
                    )
            self.call_from_thread(self._log, "[green]Sell-all complete[/]")

        self._run_in_thread(run_all)

    def _cmd_haul(self, rest: str) -> None:
        if not self._check_routine_ready():
            return
        commodity = rest.strip()
        self._haul_params = {"commodity": commodity, "buy_station": "", "sell_station": ""}
        if not commodity:
            self._haul_prompt_step = "commodity"
            self._log("Haul loop setup — enter parameters below:")
            self._log("[dim]Commodity to buy? (e.g. Aluminium)[/]")
            self.query_one("#cmd", Input).placeholder = "commodity..."
        else:
            self._log(f"Haul loop: commodity = [cyan]{escape(commodity)}[/]")
            self._haul_prompt_step = "buy_station"
            self._log("[dim]Buy station name? (press Enter to skip)[/]")
            self.query_one("#cmd", Input).placeholder = "buy station (Enter to skip)..."

    def _handle_haul_prompt(self, value: str) -> None:
        _DEFAULT_PLACEHOLDER = "dock | undock | buy <item> [N] | sell [item] | haul [commodity] | market [filter|lock|unlock] | q"
        if self._haul_prompt_step == "commodity":
            if not value.strip():
                self._log("[red]Commodity is required — enter a commodity name.[/]")
                return
            self._haul_params["commodity"] = value.strip()
            self._log(f"  Commodity: [cyan]{escape(value.strip())}[/]")
            self._haul_prompt_step = "buy_station"
            self._log("[dim]Buy station name? (press Enter to skip)[/]")
            self.query_one("#cmd", Input).placeholder = "buy station (Enter to skip)..."
        elif self._haul_prompt_step == "buy_station":
            self._haul_params["buy_station"] = value.strip()
            if value.strip():
                self._log(f"  Buy station: [cyan]{escape(value.strip())}[/]")
            else:
                self._log("  Buy station: [dim](none)[/]")
            self._haul_prompt_step = "sell_station"
            self._log("[dim]Sell station name? (press Enter to skip)[/]")
            self.query_one("#cmd", Input).placeholder = "sell station (Enter to skip)..."
        elif self._haul_prompt_step == "sell_station":
            self._haul_params["sell_station"] = value.strip()
            if value.strip():
                self._log(f"  Sell station: [cyan]{escape(value.strip())}[/]")
            else:
                self._log("  Sell station: [dim](none)[/]")
            self._haul_prompt_step = ""
            self.query_one("#cmd", Input).placeholder = _DEFAULT_PLACEHOLDER
            self._dispatch_haul_loop()

    def _dispatch_haul_loop(self) -> None:
        commodity = self._haul_params.get("commodity", "")
        buy_station = self._haul_params.get("buy_station", "")
        sell_station = self._haul_params.get("sell_station", "")

        if self._ship.status != "in_station":
            self._log("[red]Haul loop requires you to be docked at the sell station before starting.[/]")
            return
        if sell_station and self._ship.station:
            if self._ship.station.lower() != sell_station.lower():
                self._log(
                    f"[yellow]Warning: docked at [bold]{escape(self._ship.station)}[/bold] "
                    f"but sell station is [bold]{escape(sell_station)}[/bold] — "
                    f"haul loop expects you to start at the sell station.[/]"
                )
        else:
            self._log("[dim]Reminder: haul loop starts by selling cargo here, then flies to the buy station. Make sure you are docked at your sell station.[/]")

        progress = self._make_progress()
        controls = self._make_controls(progress)
        step_delay = self._config.controls.step_delay_seconds
        journal_dir = self._journal_dir
        watcher = JournalWatcher(journal_dir)

        label_parts = [f"[cyan]{escape(commodity)}[/]"]
        if buy_station:
            label_parts.append(f"buy @ [cyan]{escape(buy_station)}[/]")
        if sell_station:
            label_parts.append(f"sell @ [cyan]{escape(sell_station)}[/]")
        self._log(f"Starting haul loop: {', '.join(label_parts)} (infinite)...")
        self._routine_active = True

        self._run_in_thread(lambda: haul_loop(
            controls,
            watcher,
            journal_dir=journal_dir,
            commodity=commodity,
            buy_station=buy_station,
            sell_station=sell_station,
            step_delay_s=step_delay,
            progress_fn=progress,
        ))

    # ── Command input ──────────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        event.input.value = ""

        if self._haul_prompt_step:
            self._handle_haul_prompt(raw)
            return

        if not raw:
            return

        cmd = raw.lower()
        if cmd in {"q", "quit", "exit"}:
            self.exit()
            return

        parts = cmd.split(None, 1)
        verb = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ""
        raw_parts = raw.split(None, 1)
        raw_rest = raw_parts[1].strip() if len(raw_parts) > 1 else ""

        if verb == "dock":
            self._cmd_dock()
        elif verb == "undock":
            self._cmd_undock()
        elif verb == "jump":
            self._cmd_jump()
        elif verb == "buy":
            self._cmd_buy(rest)
        elif verb == "sell":
            self._cmd_sell(rest)
        elif verb == "haul":
            self._cmd_haul(raw_rest)
        elif verb == "market":
            self._cmd_market(rest)
        elif verb == "verbose":
            self._cmd_verbose(rest)
        elif verb in {"help", "?"}:
            self._log(
                "[dim]Routines: dock | undock | jump | buy <item> [N] | sell [item] [N] | haul [commodity]  "
                "—  Market: market [filter|lock|unlock]  —  verbose [on|off]  —  q to quit[/]"
            )
        else:
            self._log(f"[dim]Unknown command: {escape(raw)}[/]")

    def _cmd_verbose(self, rest: str) -> None:
        if rest in {"on", "1", "true"}:
            self._verbose_controls = True
            self._log("[dim]Verbose key logging on — key presses will appear in the activity log.[/]")
        elif rest in {"off", "0", "false", ""}:
            self._verbose_controls = False
            self._log("[dim]Verbose key logging off.[/]")
        else:
            state = "on" if self._verbose_controls else "off"
            self._log(f"[dim]verbose {state}  —  use: verbose on | verbose off[/]")

    def _cmd_market(self, rest: str) -> None:
        if rest == "lock":
            self._market.locked = True
            self._log("[dim]Market panel locked.[/]")
            self._refresh_market()
        elif rest == "unlock":
            self._market.locked = False
            self._log("[dim]Market panel unlocked.[/]")
            self._load_market_json()
            self._refresh_market()
        elif rest:
            self._market_filter = rest
            self._log(f"[dim]Market filter: {escape(rest)}[/]")
            self._refresh_market()
        else:
            self._market_filter = None
            self._log("[dim]Market filter cleared.[/]")
            self._refresh_market()


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
