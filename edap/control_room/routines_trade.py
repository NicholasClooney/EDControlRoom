"""Market trade routine launchers (buy, sell, sell-all)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.markup import escape

from edap.control_room import error_text
from edap.control_room.history import now_iso
from edap.control_room.interfaces import TradeHost
from edap.control_room_state import CommandHistoryEntry
from edap.routines import market_buy, market_sell


def _parse_amount(s: str) -> int | str | None:
    if s.upper() == "MAX":
        return "MAX"
    try:
        n = int(s)
        return n if n > 0 else None
    except ValueError:
        return None


def _parse_trade_target_and_amount(rest: str) -> tuple[str, int | str | None, bool]:
    value = rest.strip()
    if not value:
        return "", None, False
    parts = value.rsplit(None, 1)
    if len(parts) == 1:
        maybe_amount = _parse_amount(parts[0])
        if maybe_amount is not None:
            return "", None, True
        return parts[0], "MAX", False
    last_token = parts[1]
    maybe_amount = _parse_amount(last_token)
    if maybe_amount is None:
        if last_token.upper() == "MAX":
            return parts[0].strip(), None, True
        try:
            int(last_token)
        except ValueError:
            return value, "MAX", False
        return parts[0].strip(), None, True
    if not parts[0].strip():
        return "", None, True
    return parts[0].strip(), maybe_amount, True


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


def cmd_buy(app: TradeHost, rest: str, *, skip_delay: bool = False) -> None:
    if not app._check_routine_ready():
        return
    target, amount, _amount_supplied = _parse_trade_target_and_amount(rest)
    if not target:
        app._record_history_entry(CommandHistoryEntry(
            raw=f"buy {rest}",
            command="buy",
            params={"target": "", "amount": None},
            timestamp=now_iso(),
        ))
        app._log(f"[red]{escape(error_text.render(app._config, 'buy_usage'))}[/]")
        return
    if amount is None or not target:
        app._record_history_entry(CommandHistoryEntry(
            raw=f"buy {rest}",
            command="buy",
            params={"target": target, "amount": None},
            timestamp=now_iso(),
        ))
        app._log(f"[red]{escape(error_text.render(app._config, 'invalid_amount'))}[/]")
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

    amt_label = str(amount) + ("t" if isinstance(amount, int) else "")
    max_attempts = app._config.controls.market_trade_max_attempts
    buy_hold_seconds_per_ton = app._config.controls.market_buy_hold_seconds_per_ton
    critical_level_multiplier = app._config.controls.market_critical_level_multiplier
    app._start_delayed_routine(
        description=f"buy {target}",
        start_message=f"Buying {amt_label} [cyan]{escape(target)}[/]...",
        skip_delay=skip_delay,
        fn=lambda: market_buy(
            controls,
            watcher,
            market_path=market_path,
            target=target,
            amount=amount,
            step_delay_s=step_delay,
            nav_delay_s=nav_delay,
            max_attempts=max_attempts,
            buy_hold_seconds_per_ton=buy_hold_seconds_per_ton,
            sleeper=sleeper,
            progress_fn=progress,
            announce_fn=app._announce_tts,
            critical_level_multiplier=critical_level_multiplier,
        ),
    )


def cmd_sell(app: TradeHost, rest: str, *, skip_delay: bool = False) -> None:
    if not app._check_routine_ready():
        return
    if rest:
        target, amount, _amount_supplied = _parse_trade_target_and_amount(rest)
        if not target:
            app._record_history_entry(CommandHistoryEntry(
                raw=f"sell {rest}",
                command="sell",
                params={"target": "", "amount": None},
                timestamp=now_iso(),
            ))
            app._log(f"[red]{escape(error_text.render(app._config, 'sell_usage'))}[/]")
            return
        if amount is None or not target:
            app._record_history_entry(CommandHistoryEntry(
                raw=f"sell {rest}",
                command="sell",
                params={"target": target, "amount": None},
                timestamp=now_iso(),
            ))
            app._log(f"[red]{escape(error_text.render(app._config, 'invalid_amount'))}[/]")
            return
        app._record_history_entry(CommandHistoryEntry(
            raw=f"sell {rest}",
            command="sell",
            params={"target": target, "amount": amount},
            timestamp=now_iso(),
        ))
        sell_item(app, target, amount, skip_delay=skip_delay)
    else:
        app._record_history_entry(CommandHistoryEntry(
            raw="sell",
            command="sell",
            params={"mode": "all"},
            timestamp=now_iso(),
        ))
        sell_all(app, skip_delay=skip_delay)


def sell_item(app: TradeHost, target: str, amount: int | str, *, skip_delay: bool = False) -> None:
    progress = app._make_progress()
    controls = app._make_controls(progress)
    sleeper = app._make_sleeper()
    step_delay = app._config.controls.step_delay_seconds
    nav_delay = app._config.controls.market_nav_delay_seconds
    market_path = app._market_path
    watcher = app._make_watcher()

    amt_label = str(amount) + ("t" if isinstance(amount, int) else "")
    max_attempts = app._config.controls.market_trade_max_attempts
    buy_hold_seconds_per_ton = app._config.controls.market_buy_hold_seconds_per_ton
    critical_level_multiplier = app._config.controls.market_critical_level_multiplier
    app._start_delayed_routine(
        description=f"sell {target}",
        start_message=f"Selling {amt_label} [cyan]{escape(target)}[/]...",
        skip_delay=skip_delay,
        fn=lambda: market_sell(
            controls, watcher,
            market_path=market_path,
            target=target,
            amount=amount,
            step_delay_s=step_delay,
            nav_delay_s=nav_delay,
            max_attempts=max_attempts,
            buy_hold_seconds_per_ton=buy_hold_seconds_per_ton,
            sleeper=sleeper,
            progress_fn=progress,
            announce_fn=app._announce_tts,
            critical_level_multiplier=critical_level_multiplier,
        ),
    )


def sell_all(app: TradeHost, *, skip_delay: bool = False) -> None:
    inventory = _sellable_cargo(app._ship.cargo_inventory)
    used_fallback = False
    if not inventory:
        inventory = _sellable_cargo(_read_cargo_inventory(app._journal_dir))
        used_fallback = bool(inventory)
    if not inventory:
        app._log(f"[yellow]{escape(error_text.render(app._config, 'sell_all_empty'))}[/]")
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
        app._log(f"[yellow]{escape(error_text.render(app._config, 'sell_all_fallback'))}[/]")
    max_attempts = app._config.controls.market_trade_max_attempts
    buy_hold_seconds_per_ton = app._config.controls.market_buy_hold_seconds_per_ton
    critical_level_multiplier = app._config.controls.market_critical_level_multiplier

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
                    buy_hold_seconds_per_ton=buy_hold_seconds_per_ton,
                    sleeper=sleeper,
                    progress_fn=progress,
                    announce_fn=app._announce_tts,
                    critical_level_multiplier=critical_level_multiplier,
                )
                status = result.dispatch.status
                color = "green" if status == "ok" else "yellow"
                app.call_from_thread(app._log, f"  [{color}]{escape(name)}: {escape(status)}[/]")
            except Exception as exc:
                app.call_from_thread(
                    app._log, f"  [yellow]Skipped {escape(name)}: {escape(str(exc))}[/]"
                )
        app.call_from_thread(app._log, "[green]Sell-all complete[/]")

    app._start_delayed_routine(
        description="sell all cargo",
        start_message=f"Selling all cargo: [cyan]{escape(names)}[/]",
        skip_delay=skip_delay,
        fn=run_all,
    )
