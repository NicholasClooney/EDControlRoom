"""Market trade routine launchers (buy, sell, sell-all).

Tightly coupled to ControlRoomApp — split for file size.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.markup import escape

from edap.control_room.history import now_iso
from edap.control_room_state import CommandHistoryEntry
from edap.routines import market_buy, market_sell

if TYPE_CHECKING:
    from control_room import ControlRoomApp


def _parse_amount(s: str) -> int | str | None:
    if s.upper() == "MAX":
        return "MAX"
    try:
        n = int(s)
        return n if n > 0 else None
    except ValueError:
        return None


def _read_cargo_inventory(journal_dir: Path) -> list[dict[str, Any]]:
    cargo_path = journal_dir / "Cargo.json"
    try:
        with cargo_path.open() as fh:
            data = json.load(fh)
        inventory = data.get("Inventory", [])
        return inventory if isinstance(inventory, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _sellable_cargo(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in inventory
        if item.get("Count", 0) > 0
        and item.get("Stolen", 0) == 0
        and "MissionID" not in item
    ]


def cmd_buy(app: ControlRoomApp, rest: str) -> None:
    if not app._check_routine_ready():
        return
    parts = rest.split(None, 1)
    if not parts:
        app._log("[red]Usage: buy <item> [amount|max][/]")
        return
    target = parts[0]
    amount = _parse_amount(parts[1].strip() if len(parts) > 1 else "MAX")
    if amount is None:
        app._log(f"[red]Invalid amount — use a positive integer or MAX[/]")
        return
    app._record_history_entry(CommandHistoryEntry(
        raw=f"buy {rest}",
        command="buy",
        params={"target": target, "amount": amount},
        timestamp=now_iso(),
    ))

    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    step_delay = app._config.controls.step_delay_seconds
    nav_delay = app._config.controls.market_nav_delay_seconds
    market_path = app._market_path
    watcher = app._make_watcher()

    app._routine_active = True
    amt_label = str(amount) + ("t" if isinstance(amount, int) else "")
    app._log(f"Buying {amt_label} [cyan]{escape(target)}[/]...")
    max_attempts = app._config.controls.market_trade_max_attempts
    app._routine_worker = app._run_in_thread(lambda: market_buy(
        controls,
        watcher,
        market_path=market_path,
        target=target,
        amount=amount,
        step_delay_s=step_delay,
        nav_delay_s=nav_delay,
        max_attempts=max_attempts,
        sleeper=sleeper,
        progress_fn=progress,
    ))


def cmd_sell(app: ControlRoomApp, rest: str) -> None:
    if not app._check_routine_ready():
        return
    if rest:
        parts = rest.split(None, 1)
        target = parts[0]
        amount = _parse_amount(parts[1].strip() if len(parts) > 1 else "MAX")
        if amount is None:
            app._log("[red]Invalid amount — use a positive integer or MAX[/]")
            return
        app._record_history_entry(CommandHistoryEntry(
            raw=f"sell {rest}",
            command="sell",
            params={"target": target, "amount": amount},
            timestamp=now_iso(),
        ))
        sell_item(app, target, amount)
    else:
        app._record_history_entry(CommandHistoryEntry(
            raw="sell",
            command="sell",
            params={"mode": "all"},
            timestamp=now_iso(),
        ))
        sell_all(app)


def sell_item(app: ControlRoomApp, target: str, amount: int | str) -> None:
    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    step_delay = app._config.controls.step_delay_seconds
    nav_delay = app._config.controls.market_nav_delay_seconds
    market_path = app._market_path
    watcher = app._make_watcher()

    app._routine_active = True
    amt_label = str(amount) + ("t" if isinstance(amount, int) else "")
    app._log(f"Selling {amt_label} [cyan]{escape(target)}[/]...")
    max_attempts = app._config.controls.market_trade_max_attempts
    app._routine_worker = app._run_in_thread(lambda: market_sell(
        controls, watcher,
        market_path=market_path,
        target=target,
        amount=amount,
        step_delay_s=step_delay,
        nav_delay_s=nav_delay,
        max_attempts=max_attempts,
        sleeper=sleeper,
        progress_fn=progress,
    ))


def sell_all(app: ControlRoomApp) -> None:
    inventory = _sellable_cargo(app._ship.cargo_inventory)
    used_fallback = False
    if not inventory:
        inventory = _sellable_cargo(_read_cargo_inventory(app._journal_dir))
        used_fallback = bool(inventory)
    if not inventory:
        app._log("[yellow]Nothing sellable in cargo (empty, all stolen, or all mission cargo)[/]")
        return

    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    step_delay = app._config.controls.step_delay_seconds
    nav_delay = app._config.controls.market_nav_delay_seconds
    market_path = app._market_path
    watcher = app._make_watcher()

    names = ", ".join(item.get("Name_Localised") or item.get("Name", "?") for item in inventory)
    if used_fallback:
        app._log("[yellow]Cargo journal state was empty; using Cargo.json fallback for sell-all[/]")
    app._log(f"Selling all cargo: [cyan]{escape(names)}[/]")
    app._routine_active = True
    max_attempts = app._config.controls.market_trade_max_attempts

    def run_all() -> None:
        for item in inventory:
            app._raise_if_worker_cancelled()
            name = item.get("Name_Localised") or item.get("Name", "?")
            app.call_from_thread(app._log, f"  → [cyan]{escape(name)}[/] (MAX)...")
            try:
                result = market_sell(
                    controls, watcher,
                    market_path=market_path,
                    target=name,
                    amount="MAX",
                    step_delay_s=step_delay,
                    nav_delay_s=nav_delay,
                    max_attempts=max_attempts,
                    sleeper=sleeper,
                    progress_fn=progress,
                )
                status = result.dispatch.status
                color = "green" if status == "ok" else "yellow"
                app.call_from_thread(app._log, f"  [{color}]{escape(name)}: {escape(status)}[/]")
            except Exception as exc:
                app.call_from_thread(
                    app._log, f"  [yellow]Skipped {escape(name)}: {escape(str(exc))}[/]"
                )
        app.call_from_thread(app._log, "[green]Sell-all complete[/]")

    app._routine_worker = app._run_in_thread(run_all)
