from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from rich.markup import escape
from rich.text import Text

from edap.control_room.models import HaulStats, MarketData, ShipState
from edap.routines.market import _is_sell_market_item, _sell_market_sort_key


def fmt_cr(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M CR"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K CR"
    return f"{n:,} CR"


def fuel_bar(level: float, capacity: float) -> str:
    pct = level / capacity
    filled = round(pct * 10)
    return f"{'█' * filled}{'░' * (10 - filled)}  {round(pct * 100)}%"


def loc(item: dict[str, Any], key: str) -> str:
    return item.get(f"{key}_Localised") or item.get(key, "")


def hhmmss() -> str:
    return datetime.now().strftime("%H:%M:%S")


def is_recent(ev: dict[str, Any], threshold_s: float = 120.0) -> bool:
    ts = ev.get("timestamp", "")
    if not ts:
        return True
    try:
        ev_time = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        return (datetime.utcnow() - ev_time).total_seconds() < threshold_s
    except ValueError:
        return True


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def build_log_text(msg: str) -> Text:
    line = Text.from_markup(f"[dim]{hhmmss()}[/]  {msg}")
    line.no_wrap = False
    line.overflow = "fold"
    return line


def read_cargo_inventory(journal_dir: Path) -> list[dict[str, Any]]:
    cargo_path = journal_dir / "Cargo.json"
    try:
        with cargo_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    inventory = data.get("Inventory", [])
    return inventory if isinstance(inventory, list) else []


def cargo_summary_lines(inventory: list[dict[str, Any]], *, limit: int = 3) -> list[str]:
    rows = [item for item in inventory if int(item.get("Count", 0) or 0) > 0]
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


def destination_summary(ship: ShipState) -> str | None:
    parts = [
        ship.destination_system or None,
        ship.destination_body or None,
        ship.destination_name or None,
    ]
    filtered = [escape(str(part)) for part in parts if part]
    if not filtered:
        return None
    return " / ".join(filtered)


def status_markup(ship: ShipState) -> str:
    left_rows: list[str] = []
    right_rows: list[str] = []
    full_width_rows: list[str] = []

    def left_row(label: str, value: str) -> None:
        left_rows.append(f"[dim]{label:<11}[/]  {value}")

    def right_row(label: str, value: str) -> None:
        right_rows.append(f"[dim]{label:<11}[/]  {value}")

    if ship.commander:
        left_row("Commander", f"[bold]{escape(ship.commander)}[/]")
    left_row("System", f"[bold]{escape(ship.system or '—')}[/]")
    if ship.station:
        left_row("Station", f"[bold cyan]{escape(ship.station)}[/]")
    left_row("Status", escape(ship.status or "—"))
    if ship.fuel_level is not None and ship.fuel_capacity:
        left_row("Fuel", fuel_bar(ship.fuel_level, ship.fuel_capacity))
    destination = destination_summary(ship)
    if destination:
        full_width_rows.append(f"[dim]Destination[/]  [yellow]{destination}[/]")
    if ship.target:
        left_row("Target", f"[yellow]{escape(ship.target)}[/]")

    if ship.credits is not None:
        right_row("Balance", f"[green]{fmt_cr(ship.credits)}[/]")
    if ship.cargo_capacity is not None:
        pct = round(ship.cargo_count / ship.cargo_capacity * 100) if ship.cargo_capacity else 0
        right_row("Cargo", f"{ship.cargo_count} / {ship.cargo_capacity} t  ({pct}%)")
    elif ship.cargo_count:
        right_row("Cargo", f"{ship.cargo_count} t")

    summary = cargo_summary_lines(ship.cargo_inventory, limit=3)
    if summary:
        right_row("Cargo Top", summary[0])
        for line in summary[1:]:
            right_rows.append(f"{'':13}{line}")

    left_width = max((len(Text.from_markup(line).plain) for line in left_rows), default=0)
    paired: list[str] = []
    row_count = max(len(left_rows), len(right_rows))
    for idx in range(row_count):
        left = left_rows[idx] if idx < len(left_rows) else ""
        right = right_rows[idx] if idx < len(right_rows) else ""
        left_plain = Text.from_markup(left).plain if left else ""
        gap = " " * max(4, left_width - len(left_plain) + 4)
        paired.append(f"{left}{gap}{right}" if right else left)
    rows = paired + full_width_rows
    return "\n".join(rows) if rows else "[dim]No data yet[/]"


def haul_stats_markup(
    stats: HaulStats,
    *,
    current_balance: int | None,
    now_fn: Callable[[], float],
) -> str:
    if not stats.station_1_buying:
        lines = [
            "[dim]No haul session active.[/]",
            "",
            "Start `haul` to track cycle time,",
            "average time, and session profit.",
        ]
        if current_balance is not None:
            lines.extend(["", f"[dim]Balance[/]  [green]{fmt_cr(current_balance)}[/]"])
        return "\n".join(lines)

    rows: list[str] = []

    def row(label: str, value: str) -> None:
        rows.append(f"[dim]{label:<12}[/]  {value}")

    status = "active" if stats.active else "stopped"
    if stats.resumed_mid_run and not stats.clean_run_active:
        status = "resumed mid-run"
    elif stats.waiting_for_station_1_departure:
        status = "waiting at station 1"
    elif stats.docked_back_at_station_1:
        status = "back at station 1"

    current_elapsed = stats.current_run_elapsed_s
    if stats.current_run_started_at is not None and not stats.docked_back_at_station_1:
        current_elapsed = now_fn() - stats.current_run_started_at

    avg_elapsed = (
        stats.total_run_elapsed_s / stats.completed_runs
        if stats.completed_runs > 0 else None
    )

    row("Status", escape(status))
    row("St1 buy", f"[cyan]{escape(stats.station_1_buying)}[/]")
    row("St2 buy", f"[cyan]{escape(stats.station_2_buying)}[/]")
    row("Station 1", f"[bold cyan]{escape(stats.station_1 or '—')}[/]")
    row("Station 2", escape(stats.station_2 or "—"))
    if current_balance is not None:
        row("Balance", f"[green]{fmt_cr(current_balance)}[/]")
    row(
        "This run",
        f"[green]{fmt_cr(stats.current_run_profit)}[/]"
        if stats.clean_run_active else "[dim]—[/]",
    )
    row("Elapsed", escape(fmt_duration(current_elapsed)))
    row("Avg time", escape(fmt_duration(avg_elapsed)))
    row("Runs", str(stats.completed_runs))
    row("Accum", f"[green]{fmt_cr(stats.accumulated_profit)}[/]")
    row(
        "Last run",
        f"[green]{fmt_cr(stats.last_run_profit)}[/]"
        if stats.last_run_profit is not None else "[dim]—[/]",
    )
    row("Last time", escape(fmt_duration(stats.last_run_elapsed_s)))
    return "\n".join(rows)


def market_markup(market: MarketData, market_filter: str | None) -> str:
    if not market.items:
        return (
            "[dim]No market data.[/]\n\n"
            "Dock at a station and open\nthe market screen in-game."
        )

    lock_tag = "  [dim]\\[LOCKED][/]" if market.locked else ""
    header = (
        f"[bold]{escape(market.station)}[/] / {escape(market.system)}{lock_tag}\n"
        f"[dim]{escape(market.timestamp)}[/]"
    )

    term = market_filter.lower() if market_filter else None
    items = market.items
    if term:
        items = [
            item for item in items
            if term in loc(item, "Name").lower() or term in loc(item, "Category").lower()
        ]

    buy = [
        (loc(item, "Name"), item.get("Stock", 0), item.get("BuyPrice", 0))
        for item in items if item.get("Stock", 0) > 0
    ]
    sell_items = [item for item in items if _is_sell_market_item(item)]
    sell_items.sort(key=_sell_market_sort_key)
    sell = [
        (loc(item, "Name"), item.get("Demand", 0), item.get("SellPrice", 0))
        for item in sell_items
    ]

    sections: list[str] = [header]
    if buy:
        col = max(max(len(name) for name, *_ in buy), 12)
        sections.append("\n[bold]  BUY FROM MARKET[/]")
        sections.append(f"  [dim]{'Item':<{col}}  {'Supply':>10}  {'Buy CR':>10}[/]")
        sections.append(f"  [dim]{'─' * (col + 24)}[/]")
        for name, stock, price in sorted(buy, key=lambda row: row[0].lower()):
            sections.append(f"  {escape(name):<{col}}  {stock:>10,}  {price:>8,}")

    if sell:
        col = max(max(len(name) for name, *_ in sell), 12)
        sections.append("\n[bold]  SELL TO MARKET[/]")
        sections.append(f"  [dim]{'Item':<{col}}  {'Demand':>10}  {'Sell CR':>10}[/]")
        sections.append(f"  [dim]{'─' * (col + 24)}[/]")
        for name, demand, price in sell:
            sections.append(f"  {escape(name):<{col}}  {demand:>10,}  {price:>8,}")

    if not buy and not sell:
        no_match = f" matching '{escape(term)}'" if term else ""
        sections.append(f"\n[dim]No items{no_match}.[/]")

    return "\n".join(sections)


def activity_line(ev: dict[str, Any]) -> str | None:
    if not is_recent(ev):
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
        return f"Bought [cyan]{ev.get('Count')}t {name}[/]  [dim]{fmt_cr(ev.get('TotalCost', 0))}[/]"
    if event == "MarketSell":
        name = escape(ev.get("Type_Localised") or ev.get("Type", "?"))
        return f"Sold [cyan]{ev.get('Count')}t {name}[/]  →  [green]{fmt_cr(ev.get('TotalSale', 0))}[/]"
    if event == "Refuelled":
        return f"Refuelled {ev.get('Amount', 0):.1f}t"
    if event == "MissionCompleted":
        label = escape(ev.get("LocalisedName") or ev.get("Name", "mission"))
        return f"Mission: {label}  →  [green]{fmt_cr(ev.get('Reward', 0))}[/]"
    return None
