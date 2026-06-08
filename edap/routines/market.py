from __future__ import annotations

import json
from pathlib import Path
from time import monotonic, sleep
from typing import Callable

from edap.actions import ActionDispatchResult
from edap.routines._base import (
    RoutineResult,
    SupportsMarketControls,
    SupportsPollEvents,
    _wait_for_event_with_pending,
)
from edap.tts import AnnouncementId


def _market_localised(item: dict, key: str) -> str:
    return item.get(f"{key}_Localised") or item.get(key, "")


def _market_buy_list(items: list[dict]) -> list[tuple[str, str]]:
    rows = [
        (_market_localised(it, "Category"), _market_localised(it, "Name"))
        for it in items
        if it.get("Stock", 0) > 0
    ]
    return sorted(rows, key=lambda r: (r[0].lower(), r[1].lower()))


def _market_sell_list(items: list[dict]) -> list[tuple[str, str]]:
    # DemandBracket > 0 matches the in-game sell tab. Items with Demand=1 and
    # bracket=0 are placeholders the game does not display or accept.
    rows = [
        (_market_localised(it, "Category"), _market_localised(it, "Name"))
        for it in items
        if it.get("DemandBracket", 0) > 0
    ]
    return sorted(rows, key=lambda r: (r[0].lower(), r[1].lower()))


def _market_item_index(sorted_items: list[tuple[str, str]], target: str) -> int:
    t = target.lower()
    for i, (_, name) in enumerate(sorted_items):
        if name.lower() == t:
            return i
    sample = [name for _, name in sorted_items[:5]]
    suffix = "..." if len(sorted_items) > 5 else ""
    raise ValueError(f"'{target}' not found in market list (first items: {sample}{suffix})")


def _is_market_event(event: dict[str, object], event_type: str, target: str) -> bool:
    if event.get("event") != event_type:
        return False
    t = target.lower()
    # Exact match (case-insensitive) so a wrong commodity cannot satisfy the
    # predicate -- e.g. a stray MarketBuy for "Gold" must not match target "Gold Ore".
    return (
        str(event.get("Type_Localised", "")).lower() == t
        or str(event.get("Type", "")).lower() == t
    )


def _read_last_docked_state(journal_dir: Path) -> dict[str, object] | None:
    journal_files = sorted(journal_dir.glob("Journal.*.log"))
    if not journal_files:
        return None
    try:
        lines = journal_files[-1].read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("event") == "Docked":
                return event
            if event.get("event") in {"Location", "CarrierJump"} and event.get("Docked") is True:
                return event
        except json.JSONDecodeError:
            continue
    return None


def _read_last_cargo_capacity(journal_dir: Path) -> int | None:
    journal_files = sorted(journal_dir.glob("Journal.*.log"))
    if not journal_files:
        return None
    for journal_file in reversed(journal_files):
        try:
            lines = journal_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            cargo_capacity = event.get("CargoCapacity")
            if isinstance(cargo_capacity, (int, float)) and cargo_capacity > 0:
                return int(cargo_capacity)
    return None


def _find_market_item(items: list[dict], target: str, side: str) -> dict | None:
    target_lower = target.lower()
    for item in items:
        if side == "buy" and item.get("Stock", 0) <= 0:
            continue
        if side == "sell" and item.get("DemandBracket", 0) <= 0:
            continue
        if (
            _market_localised(item, "Name").lower() == target_lower
            or str(item.get("Name", "")).lower() == target_lower
        ):
            return item
    return None


def _report_market_level(
    item: dict,
    *,
    journal_dir: Path,
    side: str,
    critical_level_multiplier: float,
    progress_fn: Callable[[str], None] | None,
    announce_fn: Callable[..., None] | None,
) -> None:
    units_key = "Stock" if side == "buy" else "Demand"
    market_side = "supply" if side == "buy" else "demand"
    units = int(item.get(units_key, 0) or 0)
    commodity_name = _market_localised(item, "Name") or str(item.get("Name", ""))
    cargo_capacity = _read_last_cargo_capacity(journal_dir)
    if cargo_capacity is None or cargo_capacity <= 0:
        if progress_fn is not None:
            progress_fn(
                f"Station {market_side} for {commodity_name} is {units} units; "
                "cargo capacity unavailable, skipping low-level threshold check."
            )
        return

    low_threshold = int(cargo_capacity * critical_level_multiplier)
    if units < low_threshold:
        if progress_fn is not None:
            progress_fn(
                f"Warning: Station {market_side} for {commodity_name} is low at "
                f"{units} units (critical below {low_threshold})."
            )
        if announce_fn is not None:
            announce_fn(
                AnnouncementId.MARKET_LEVEL_LOW,
                market_side=market_side,
                commodity_name=commodity_name,
                units=units,
            )
        return

    if progress_fn is not None:
        progress_fn(
            f"Station {market_side} for {commodity_name} looks normal at "
            f"{units} units (critical below {low_threshold})."
        )


def _market_error(action: str, reason: str) -> RoutineResult:
    return RoutineResult(
        action=action,
        dispatch=ActionDispatchResult(action=action, status="error", reason=reason),
    )


def market_buy(
    controls: SupportsMarketControls,
    watcher: SupportsPollEvents,
    *,
    market_path: Path,
    target: str,
    amount: int | str,
    step_delay_s: float = 1.0,
    nav_delay_s: float = 0.1,
    max_hold_s: float = 10.0,
    trade_timeout_s: float = 30.0,
    skip_station_check: bool = False,
    max_attempts: int = 3,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: Callable[[str], None] | None = None,
    announce_fn: Callable[..., None] | None = None,
    critical_level_multiplier: float = 10.0,
) -> RoutineResult:
    return _market_trade(
        controls, watcher,
        market_path=market_path, target=target, amount=amount, side="buy",
        step_delay_s=step_delay_s, nav_delay_s=nav_delay_s, max_hold_s=max_hold_s,
        trade_timeout_s=trade_timeout_s, skip_station_check=skip_station_check,
        max_attempts=max_attempts,
        time_fn=time_fn, sleeper=sleeper, progress_fn=progress_fn, announce_fn=announce_fn,
        critical_level_multiplier=critical_level_multiplier,
    )


def market_sell(
    controls: SupportsMarketControls,
    watcher: SupportsPollEvents,
    *,
    market_path: Path,
    target: str,
    amount: int | str,
    step_delay_s: float = 1.0,
    nav_delay_s: float = 0.1,
    max_hold_s: float = 10.0,
    trade_timeout_s: float = 30.0,
    skip_station_check: bool = False,
    max_attempts: int = 3,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: Callable[[str], None] | None = None,
    announce_fn: Callable[..., None] | None = None,
    critical_level_multiplier: float = 10.0,
) -> RoutineResult:
    return _market_trade(
        controls, watcher,
        market_path=market_path, target=target, amount=amount, side="sell",
        step_delay_s=step_delay_s, nav_delay_s=nav_delay_s, max_hold_s=max_hold_s,
        trade_timeout_s=trade_timeout_s, skip_station_check=skip_station_check,
        max_attempts=max_attempts,
        time_fn=time_fn, sleeper=sleeper, progress_fn=progress_fn, announce_fn=announce_fn,
        critical_level_multiplier=critical_level_multiplier,
    )


def _market_trade(
    controls: SupportsMarketControls,
    watcher: SupportsPollEvents,
    *,
    market_path: Path,
    target: str,
    amount: int | str,
    side: str,
    step_delay_s: float,
    nav_delay_s: float,
    max_hold_s: float,
    trade_timeout_s: float,
    skip_station_check: bool,
    max_attempts: int,
    time_fn: Callable[[], float],
    sleeper: Callable[[float], None],
    progress_fn: Callable[[str], None] | None,
    announce_fn: Callable[..., None] | None,
    critical_level_multiplier: float,
) -> RoutineResult:
    event_type = "MarketBuy" if side == "buy" else "MarketSell"
    if max_attempts < 1:
        max_attempts = 1

    last_failure: RoutineResult | None = None
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            if progress_fn is not None:
                progress_fn(
                    f"Retrying {side} of '{target}' "
                    f"(attempt {attempt}/{max_attempts})..."
                )
            # Bail out of any lingering dialog/list back to station services
            for _ in range(4):
                controls.ui_back()
                if nav_delay_s > 0:
                    sleeper(nav_delay_s)

        result = _market_trade_attempt(
            controls, watcher,
            market_path=market_path, target=target, amount=amount, side=side,
            event_type=event_type,
            step_delay_s=step_delay_s, nav_delay_s=nav_delay_s, max_hold_s=max_hold_s,
            trade_timeout_s=trade_timeout_s, skip_station_check=skip_station_check,
            time_fn=time_fn, sleeper=sleeper, progress_fn=progress_fn, announce_fn=announce_fn,
            critical_level_multiplier=critical_level_multiplier,
        )

        if result.dispatch.status == "ok" and result.trigger_event is not None:
            return result

        # Only the wait-for-event phase is retryable; other failures (UI dispatch,
        # missing Market.json, item not in list) indicate setup problems that won't
        # be fixed by trying again.
        phase = (result.details or {}).get("phase", "")
        if phase != "wait_for_event":
            return result

        last_failure = result

    assert last_failure is not None
    base_reason = last_failure.dispatch.reason or "no event observed"
    return _market_error(
        event_type,
        f"{event_type} for '{target}' failed after {max_attempts} "
        f"attempts: {base_reason}",
    )


def _market_trade_attempt(
    controls: SupportsMarketControls,
    watcher: SupportsPollEvents,
    *,
    market_path: Path,
    target: str,
    amount: int | str,
    side: str,
    event_type: str,
    step_delay_s: float,
    nav_delay_s: float,
    max_hold_s: float,
    trade_timeout_s: float,
    skip_station_check: bool,
    time_fn: Callable[[], float],
    sleeper: Callable[[float], None],
    progress_fn: Callable[[str], None] | None,
    announce_fn: Callable[..., None] | None,
    critical_level_multiplier: float,
) -> RoutineResult:
    # Navigate to commodities market first -- the game writes Market.json when the screen opens
    if progress_fn is not None:
        progress_fn("Navigating to commodities market...")

    if progress_fn is not None:
        progress_fn("  UI_Select (enter station services)")
    dispatch = controls.ui_select()
    if dispatch.status != "ok":
        return RoutineResult(action=dispatch.action, dispatch=dispatch, details={"phase": "navigate_to_market"})
    # Station services UI takes a moment to populate after selection
    sleeper(7.0)

    for fn, label, delay in [
        (controls.ui_down, "UI_Down (to commodities market)", nav_delay_s),
        (controls.ui_select, "UI_Select (open market)", step_delay_s),
    ]:
        if progress_fn is not None:
            progress_fn(f"  {label}")
        dispatch = fn()
        if dispatch.status != "ok":
            return RoutineResult(action=dispatch.action, dispatch=dispatch, details={"phase": "navigate_to_market"})
        if delay > 0:
            sleeper(delay)

    sleeper(5.0)

    # Verify Market.json matches the current docked station.
    # The game writes it when the market screen opens; retry up to 3 times if delayed.
    data: dict = {}
    if skip_station_check:
        if not market_path.exists():
            return _market_error(event_type, "Market.json not found")
        with market_path.open() as fh:
            data = json.load(fh)
        if progress_fn is not None:
            progress_fn("Station check skipped")
    else:
        _RETRIES = 3
        _RETRY_DELAY_S = 10.0
        for attempt in range(1, _RETRIES + 1):
            fail_reason: str | None = None
            if not market_path.exists():
                fail_reason = "Market.json not found"
            else:
                with market_path.open() as fh:
                    data = json.load(fh)
                docked = _read_last_docked_state(market_path.parent)
                if docked is None:
                    fail_reason = (
                        "no docked station state found in journal "
                        "(expected Docked or Location(Docked=true)) -- cannot verify current station"
                    )
                else:
                    market_id = data.get("MarketID")
                    docked_id = docked.get("MarketID")
                    if market_id and docked_id and market_id == docked_id:
                        pass  # confirmed match
                    elif data.get("StationName") and data.get("StationName") == docked.get("StationName"):
                        pass  # fallback name match
                    else:
                        fail_reason = (
                            f"Market.json is from {data.get('StationName', '?')!r} "
                            f"but last Docked event is {docked.get('StationName', '?')!r}"
                        )
            if fail_reason is None:
                break
            if attempt < _RETRIES:
                if progress_fn is not None:
                    progress_fn(f"Station check failed (attempt {attempt}/{_RETRIES}): {fail_reason}")
                    progress_fn(f"  Retrying in {_RETRY_DELAY_S:.0f}s...")
                sleeper(_RETRY_DELAY_S)
            else:
                return _market_error(event_type, f"Station check failed after {_RETRIES} attempts: {fail_reason}")

    items: list[dict] = data.get("Items", [])

    sorted_items = _market_buy_list(items) if side == "buy" else _market_sell_list(items)
    try:
        item_index = _market_item_index(sorted_items, target)
    except ValueError as exc:
        return _market_error(event_type, str(exc))
    item = _find_market_item(items, target, side)
    if item is None:
        return _market_error(event_type, f"'{target}' matched navigation list but not market item data")

    if progress_fn is not None:
        progress_fn(f"Target '{target}' at position {item_index} in {side} list ({len(sorted_items)} items)")
    _report_market_level(
        item,
        journal_dir=market_path.parent,
        side=side,
        critical_level_multiplier=critical_level_multiplier,
        progress_fn=progress_fn,
        announce_fn=announce_fn,
    )

    # For sell: navigate sidebar from BUY to SELL tab before entering the list
    if side == "sell":
        if progress_fn is not None:
            progress_fn("  UI_Down (BUY -> SELL tab)")
        dispatch = controls.ui_down()
        if dispatch.status != "ok":
            return RoutineResult(action="UI_Down", dispatch=dispatch, details={"phase": "navigate_to_sell_tab"})
        if nav_delay_s > 0:
            sleeper(nav_delay_s)

        if progress_fn is not None:
            progress_fn("  UI_Select (enter SELL tab)")
        dispatch = controls.ui_select()
        if dispatch.status != "ok":
            return RoutineResult(action="UI_Select", dispatch=dispatch, details={"phase": "navigate_to_sell_tab"})
        if step_delay_s > 0:
            sleeper(step_delay_s)

    # Enter the commodity list (cursor lands on the first item)
    if progress_fn is not None:
        progress_fn("  UI_Right (enter commodity list)")
    dispatch = controls.ui_right()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Right", dispatch=dispatch, details={"phase": "enter_list"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    # Navigate down to target item (category headers are non-navigable separators)
    if item_index > 0:
        if progress_fn is not None:
            progress_fn(f"  UI_Down x{item_index} (navigate to '{target}')")
        for _ in range(item_index):
            dispatch = controls.ui_down()
            if dispatch.status != "ok":
                return RoutineResult(action="UI_Down", dispatch=dispatch, details={"phase": "navigate_to_item"})
            if nav_delay_s > 0:
                sleeper(nav_delay_s)

    # Open the trade dialog for this item
    if progress_fn is not None:
        progress_fn(f"  UI_Select (open '{target}' dialog)")
    dispatch = controls.ui_select()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Select", dispatch=dispatch, details={"phase": "select_item"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    # Prime the watcher before setting quantity so the trade event is not missed
    pending_events = watcher.poll()

    # Set quantity
    # Set quantity -- sell pre-fills with full cargo amount so no input needed
    if side == "buy":
        if amount == "MAX":
            if progress_fn is not None:
                progress_fn(f"  UI_Right hold {max_hold_s:.0f}s (fill to max)")
            qty_dispatch = controls.ui_right(hold_s=max_hold_s)
            if qty_dispatch.status != "ok":
                return RoutineResult(action="UI_Right", dispatch=qty_dispatch, details={"phase": "set_quantity"})
        else:
            qty = int(amount)
            if progress_fn is not None:
                progress_fn(f"  UI_Right x{qty} (set quantity to {qty})")
            qty_dispatch = None
            for _ in range(qty):
                qty_dispatch = controls.ui_right()
                if qty_dispatch.status != "ok":
                    return RoutineResult(action="UI_Right", dispatch=qty_dispatch, details={"phase": "set_quantity"})
                if step_delay_s > 0:
                    sleeper(step_delay_s)
            if qty_dispatch is None:
                return _market_error(event_type, "amount must be at least 1")
        if step_delay_s > 0:
            sleeper(step_delay_s)

    # Confirm trade
    confirm_label = "BUY" if side == "buy" else "SELL"
    if progress_fn is not None:
        progress_fn(f"  UI_Down (to {confirm_label} button)")
    dispatch = controls.ui_down()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Down", dispatch=dispatch, details={"phase": "confirm"})
    if nav_delay_s > 0:
        sleeper(nav_delay_s)

    if progress_fn is not None:
        progress_fn(f"  UI_Select (confirm {confirm_label})")
    trade_dispatch = controls.ui_select()
    if trade_dispatch.status != "ok":
        return RoutineResult(action="UI_Select", dispatch=trade_dispatch, details={"phase": "confirm"})

    # Wait for journal confirmation
    if progress_fn is not None:
        progress_fn(f"Waiting for {event_type} event (timeout {trade_timeout_s:.0f}s)...")
    trade_event, _ = _wait_for_event_with_pending(
        watcher,
        predicate=lambda e: _is_market_event(e, event_type, target),
        deadline=time_fn() + trade_timeout_s,
        time_fn=time_fn,
        pending_events=pending_events,
    )
    if trade_event is None:
        return RoutineResult(
            action=event_type,
            dispatch=ActionDispatchResult(
                action=event_type,
                status="error",
                reason=f"{event_type} for '{target}' not observed within {trade_timeout_s:.0f}s",
            ),
            details={"phase": "wait_for_event"},
        )

    if progress_fn is not None:
        count = trade_event.get("Count", "?")
        cr_key = "TotalCost" if side == "buy" else "TotalSale"
        cr_val = trade_event.get(cr_key, "?")
        progress_fn(f"{event_type}: {count}x {target}, {cr_val} CR total")

    # Return to station menu
    if progress_fn is not None:
        progress_fn("  UI_Back x2 (return to station menu)")
    back_dispatch = controls.ui_back()
    if back_dispatch.status != "ok":
        return RoutineResult(
            action="UI_Back",
            dispatch=back_dispatch,
            trigger_event=trade_event,
            details={"phase": "return_to_station_menu"},
        )
    if step_delay_s > 0:
        sleeper(step_delay_s)
    back_dispatch = controls.ui_back()
    if back_dispatch.status != "ok":
        return RoutineResult(
            action="UI_Back",
            dispatch=back_dispatch,
            trigger_event=trade_event,
            details={"phase": "return_to_station_menu"},
        )

    return RoutineResult(
        action=event_type,
        dispatch=trade_dispatch,
        trigger_event=trade_event,
        details={"target": target, "amount": str(amount), "side": side},
    )
