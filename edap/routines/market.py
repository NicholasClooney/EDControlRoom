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
from edap.routines._callbacks import AnnouncementCallback, ProgressCallback
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


def _is_sell_market_item(item: dict) -> bool:
    demand_bracket = int(item.get("DemandBracket", 0) or 0)
    sell_price = int(item.get("SellPrice", 0) or 0)
    # Elite can let the player sell cargo the station is not actively buying.
    # In Market.json that often shows up as DemandBracket == 0 with a non-zero
    # SellPrice. Treat those rows as intentionally sellable so EDAP can still
    # target and offload the player's existing cargo there.
    #
    # Keep excluding placeholder rows that have neither demand nor a sell price.
    return demand_bracket > 0 or sell_price > 0


def _market_sell_list(items: list[dict]) -> list[tuple[str, str]]:
    rows = [
        (_market_localised(it, "Category"), _market_localised(it, "Name"))
        for it in items
        if int(it.get("DemandBracket", 0) or 0) > 0
    ]
    return sorted(rows, key=lambda r: (r[0].lower(), r[1].lower()))


def _market_sell_list_for_target(items: list[dict], target_item: dict | None) -> list[tuple[str, str]]:
    rows = _market_sell_list(items)
    if target_item is None or not _is_sell_market_item(target_item):
        return rows
    target_row = (
        _market_localised(target_item, "Category"),
        _market_localised(target_item, "Name"),
    )
    if any(name.lower() == target_row[1].lower() for _, name in rows):
        return rows
    # The visible SELL list is demand-based, but the game can still accept a
    # sale for cargo already in the player's hold even when that commodity does
    # not appear in the station's normal buy list. When Market.json exposes a
    # price for the target, inject just that target row so cursor indexing still
    # lines up with the game behavior we intentionally support.
    rows = rows + [target_row]
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


def _read_latest_position_state(journal_dir: Path) -> dict[str, object] | None:
    journal_files = sorted(journal_dir.glob("Journal.*.log"))
    if not journal_files:
        return None
    position_event_types = {"Docked", "Undocked", "SupercruiseEntry", "SupercruiseExit", "Location", "FSDJump"}
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
            if event.get("event") in position_event_types:
                return event
    return None


def _is_currently_docked(journal_dir: Path) -> tuple[bool, str]:
    latest_position = _read_latest_position_state(journal_dir)
    if latest_position is None:
        return False, "no current station state found in journal"
    event_name = str(latest_position.get("event", ""))
    if event_name == "Docked":
        return True, ""
    if event_name == "Location":
        if latest_position.get("Docked") is True:
            return True, ""
        return False, "latest position event is Location(Docked=false)"
    return False, f"latest position event is {event_name}"


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


def _read_available_cargo_space(journal_dir: Path) -> int | None:
    cargo_capacity = _read_last_cargo_capacity(journal_dir)
    if cargo_capacity is None or cargo_capacity <= 0:
        return None
    cargo_path = journal_dir / "Cargo.json"
    try:
        with cargo_path.open(encoding="utf-8") as handle:
            cargo_data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    inventory = cargo_data.get("Inventory", [])
    if not isinstance(inventory, list):
        return None
    used_capacity = 0
    for item in inventory:
        if not isinstance(item, dict):
            return None
        count = item.get("Count", 0)
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            return None
        used_capacity += int(count)
    return max(0, cargo_capacity - used_capacity)


def _read_cargo_inventory(journal_dir: Path) -> list[dict] | None:
    cargo_path = journal_dir / "Cargo.json"
    try:
        with cargo_path.open(encoding="utf-8") as handle:
            cargo_data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    inventory = cargo_data.get("Inventory", [])
    if not isinstance(inventory, list):
        return None
    return inventory


def _read_sell_quantity(journal_dir: Path, target: str) -> int | None:
    inventory = _read_cargo_inventory(journal_dir)
    if inventory is None:
        return None
    target_lower = target.lower()
    for item in inventory:
        if not isinstance(item, dict):
            return None
        if (
            str(item.get("Name", "")).lower() != target_lower
            and str(item.get("Name_Localised", "")).lower() != target_lower
        ):
            continue
        count = item.get("Count", 0)
        if isinstance(count, bool) or not isinstance(count, (int, float)) or count < 0:
            return None
        return int(count)
    return None


def _find_market_item(items: list[dict], target: str, side: str) -> dict | None:
    target_lower = target.lower()
    for item in items:
        if side == "buy" and item.get("Stock", 0) <= 0:
            continue
        if side == "sell" and not _is_sell_market_item(item):
            continue
        if (
            _market_localised(item, "Name").lower() == target_lower
            or str(item.get("Name", "")).lower() == target_lower
        ):
            return item
    return None


def _read_buy_quantity_limit(
    journal_dir: Path,
    item: dict,
) -> tuple[int | None, str]:
    available_space = _read_available_cargo_space(journal_dir)
    stock = item.get("Stock", 0)
    stock_units = int(stock) if isinstance(stock, (int, float)) and not isinstance(stock, bool) else None
    if stock_units is not None:
        stock_units = max(0, stock_units)

    if available_space is not None and stock_units is not None:
        return min(available_space, stock_units), f"from min({available_space}t free, {stock_units}t supply)"
    if available_space is not None:
        return available_space, f"from {available_space}t free"
    if stock_units is not None:
        return stock_units, f"from {stock_units}t supply"
    return None, "cargo space and station supply unavailable"


def _report_market_level(
    item: dict,
    *,
    journal_dir: Path,
    side: str,
    critical_level_multiplier: float,
    progress_fn: ProgressCallback,
    announce_fn: AnnouncementCallback,
) -> None:
    units_key = "Stock" if side == "buy" else "Demand"
    market_side = "supply" if side == "buy" else "demand"
    units = int(item.get(units_key, 0) or 0)
    commodity_name = _market_localised(item, "Name") or str(item.get("Name", ""))
    cargo_capacity = _read_last_cargo_capacity(journal_dir)
    if cargo_capacity is None or cargo_capacity <= 0:
        progress_fn(
            f"Station {market_side} for {commodity_name} is {units} units; "
            "cargo capacity unavailable, skipping low-level threshold check."
        )
        return

    low_threshold = int(cargo_capacity * critical_level_multiplier)
    if units < low_threshold:
        progress_fn(
            f"Warning: Station {market_side} for {commodity_name} is low at "
            f"{units} units (critical below {low_threshold})."
        )
        announce_fn(
            AnnouncementId.MARKET_LEVEL_LOW,
            market_side=market_side,
            commodity_name=commodity_name,
            units=units,
        )
        return

    progress_fn(
        f"Station {market_side} for {commodity_name} looks normal at "
        f"{units} units (critical below {low_threshold})."
    )


def _market_error(action: str, reason: str) -> RoutineResult:
    return RoutineResult(
        action=action,
        dispatch=ActionDispatchResult(action=action, status="error", reason=reason),
    )


def _market_ui_reset(
    controls: SupportsMarketControls,
    *,
    step_delay_s: float,
    sleeper: Callable[[float], None],
    progress_fn: ProgressCallback,
) -> ActionDispatchResult:
    progress_fn("Resetting UI state...")
    progress_fn("  UI_Back x4 (reset to station menu)")
    dispatch = ActionDispatchResult(action="UI_Back", status="ok")
    for _ in range(4):
        dispatch = controls.ui_back()
        if dispatch.status != "ok":
            return dispatch
        if step_delay_s > 0:
            sleeper(step_delay_s)
    return dispatch


def _market_back_out_to_station_menu(
    controls: SupportsMarketControls,
    *,
    step_delay_s: float,
    sleeper: Callable[[float], None],
    progress_fn: ProgressCallback,
) -> ActionDispatchResult:
    progress_fn("  UI_Back x4 (return to station menu)")
    dispatch = ActionDispatchResult(action="UI_Back", status="ok")
    for _ in range(4):
        dispatch = controls.ui_back()
        if dispatch.status != "ok":
            return dispatch
        if step_delay_s > 0:
            sleeper(step_delay_s)
    return dispatch


def _market_reset_trade_dialog_focus(
    controls: SupportsMarketControls,
    *,
    nav_delay_s: float,
    sleeper: Callable[[float], None],
    progress_fn: ProgressCallback,
) -> ActionDispatchResult:
    progress_fn("Resetting trade dialog focus to quantity controls...")
    progress_fn("  UI_Left x3 (bias to left edge of dialog)")
    dispatch = ActionDispatchResult(action="UI_Left", status="ok")
    for _ in range(3):
        dispatch = controls.ui_left()
        if dispatch.status != "ok":
            return dispatch
        if nav_delay_s > 0:
            sleeper(nav_delay_s)

    progress_fn("  UI_Up x3 (bias to quantity row)")
    dispatch = ActionDispatchResult(action="UI_Up", status="ok")
    for _ in range(3):
        dispatch = controls.ui_up()
        if dispatch.status != "ok":
            return dispatch
        if nav_delay_s > 0:
            sleeper(nav_delay_s)
    return dispatch


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
    buy_hold_seconds_per_ton: float = 0.01,
    trade_timeout_s: float = 30.0,
    skip_station_check: bool = False,
    max_attempts: int = 3,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: ProgressCallback,
    announce_fn: AnnouncementCallback,
    critical_level_multiplier: float = 10.0,
) -> RoutineResult:
    return _market_trade(
        controls, watcher,
        market_path=market_path, target=target, amount=amount, side="buy",
        step_delay_s=step_delay_s, nav_delay_s=nav_delay_s, max_hold_s=max_hold_s,
        buy_hold_seconds_per_ton=buy_hold_seconds_per_ton,
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
    buy_hold_seconds_per_ton: float = 0.01,
    trade_timeout_s: float = 30.0,
    skip_station_check: bool = False,
    max_attempts: int = 3,
    time_fn: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    progress_fn: ProgressCallback,
    announce_fn: AnnouncementCallback,
    critical_level_multiplier: float = 10.0,
) -> RoutineResult:
    return _market_trade(
        controls, watcher,
        market_path=market_path, target=target, amount=amount, side="sell",
        step_delay_s=step_delay_s, nav_delay_s=nav_delay_s, max_hold_s=max_hold_s,
        buy_hold_seconds_per_ton=buy_hold_seconds_per_ton,
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
    buy_hold_seconds_per_ton: float,
    trade_timeout_s: float,
    skip_station_check: bool,
    max_attempts: int,
    time_fn: Callable[[], float],
    sleeper: Callable[[float], None],
    progress_fn: ProgressCallback,
    announce_fn: AnnouncementCallback,
    critical_level_multiplier: float,
) -> RoutineResult:
    event_type = "MarketBuy" if side == "buy" else "MarketSell"
    if max_attempts < 1:
        max_attempts = 1

    last_failure: RoutineResult | None = None
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
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
            buy_hold_seconds_per_ton=buy_hold_seconds_per_ton,
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
    buy_hold_seconds_per_ton: float,
    trade_timeout_s: float,
    skip_station_check: bool,
    time_fn: Callable[[], float],
    sleeper: Callable[[float], None],
    progress_fn: ProgressCallback,
    announce_fn: AnnouncementCallback,
    critical_level_multiplier: float,
) -> RoutineResult:
    if side == "sell":
        docked, reason = _is_currently_docked(market_path.parent)
        if not docked:
            return _market_error(event_type, f"sell requires an in-station start: {reason}")

    dispatch = _market_ui_reset(
        controls,
        step_delay_s=step_delay_s,
        sleeper=sleeper,
        progress_fn=progress_fn,
    )
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Back", dispatch=dispatch, details={"phase": "reset"})

    # Navigate to commodities market first -- the game writes Market.json when the screen opens
    progress_fn("Navigating to commodities market...")

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
                progress_fn(f"Station check failed (attempt {attempt}/{_RETRIES}): {fail_reason}")
                progress_fn(f"  Retrying in {_RETRY_DELAY_S:.0f}s...")
                sleeper(_RETRY_DELAY_S)
            else:
                return _market_error(event_type, f"Station check failed after {_RETRIES} attempts: {fail_reason}")

    items: list[dict] = data.get("Items", [])

    item = _find_market_item(items, target, side)
    sorted_items = (
        _market_buy_list(items)
        if side == "buy"
        else _market_sell_list_for_target(items, item)
    )
    try:
        item_index = _market_item_index(sorted_items, target)
    except ValueError as exc:
        return _market_error(event_type, str(exc))
    if item is None:
        return _market_error(event_type, f"'{target}' matched navigation list but not market item data")

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
        progress_fn("  UI_Down (BUY -> SELL tab)")
        dispatch = controls.ui_down()
        if dispatch.status != "ok":
            return RoutineResult(action="UI_Down", dispatch=dispatch, details={"phase": "navigate_to_sell_tab"})
        if nav_delay_s > 0:
            sleeper(nav_delay_s)

        progress_fn("  UI_Select (enter SELL tab)")
        dispatch = controls.ui_select()
        if dispatch.status != "ok":
            return RoutineResult(action="UI_Select", dispatch=dispatch, details={"phase": "navigate_to_sell_tab"})
        if step_delay_s > 0:
            sleeper(step_delay_s)

    # Enter the commodity list (cursor lands on the first item)
    progress_fn("  UI_Right (enter commodity list)")
    dispatch = controls.ui_right()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Right", dispatch=dispatch, details={"phase": "enter_list"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    # Navigate down to target item (category headers are non-navigable separators)
    if item_index > 0:
        progress_fn(f"  UI_Down x{item_index} (navigate to '{target}')")
        for _ in range(item_index):
            dispatch = controls.ui_down()
            if dispatch.status != "ok":
                return RoutineResult(action="UI_Down", dispatch=dispatch, details={"phase": "navigate_to_item"})
            if nav_delay_s > 0:
                sleeper(nav_delay_s)

    # Open the trade dialog for this item
    progress_fn(f"  UI_Select (open '{target}' dialog)")
    dispatch = controls.ui_select()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Select", dispatch=dispatch, details={"phase": "select_item"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    dialog_reset_dispatch = _market_reset_trade_dialog_focus(
        controls,
        nav_delay_s=nav_delay_s,
        sleeper=sleeper,
        progress_fn=progress_fn,
    )
    if dialog_reset_dispatch.status != "ok":
        return RoutineResult(
            action=dialog_reset_dispatch.action,
            dispatch=dialog_reset_dispatch,
            details={"phase": "reset_trade_dialog_focus"},
        )

    # Prime the watcher before setting quantity so the trade event is not missed
    pending_events = watcher.poll()

    # Set quantity
    if side == "buy":
        if amount == "MAX":
            hold_s = max_hold_s
            buy_limit, buy_limit_reason = _read_buy_quantity_limit(market_path.parent, item)
            if buy_limit is not None:
                hold_s = min(max_hold_s, buy_limit * buy_hold_seconds_per_ton)
            if buy_limit is None:
                progress_fn(
                    f"  UI_Right hold {hold_s:.2f}s "
                    f"(fill to max; {buy_limit_reason}, using cap)"
                )
            else:
                progress_fn(
                    f"  UI_Right hold {hold_s:.2f}s "
                    f"(fill to max {buy_limit_reason} at {buy_hold_seconds_per_ton:.4f}s/t)"
                )
            qty_dispatch = controls.ui_right(hold_s=hold_s)
            if qty_dispatch.status != "ok":
                return RoutineResult(action="UI_Right", dispatch=qty_dispatch, details={"phase": "set_quantity"})
        else:
            qty = int(amount)
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
    else:
        sell_qty = int(amount) if amount != "MAX" else _read_sell_quantity(market_path.parent, target)
        hold_s = max_hold_s
        if sell_qty is not None:
            hold_s = min(max_hold_s, sell_qty * buy_hold_seconds_per_ton)
        if sell_qty is None:
            progress_fn(
                f"  UI_Right hold {hold_s:.2f}s (restore sell quantity; cargo count unavailable, using cap)"
            )
        else:
            progress_fn(
                f"  UI_Right hold {hold_s:.2f}s "
                f"(restore sell quantity to {sell_qty}t at {buy_hold_seconds_per_ton:.4f}s/t)"
            )
        qty_dispatch = controls.ui_right(hold_s=hold_s)
        if qty_dispatch.status != "ok":
            return RoutineResult(action="UI_Right", dispatch=qty_dispatch, details={"phase": "set_quantity"})
    if step_delay_s > 0:
        sleeper(step_delay_s)

    # Confirm trade
    confirm_label = "BUY" if side == "buy" else "SELL"
    progress_fn(f"  UI_Down (to {confirm_label} button)")
    dispatch = controls.ui_down()
    if dispatch.status != "ok":
        return RoutineResult(action="UI_Down", dispatch=dispatch, details={"phase": "confirm"})
    if nav_delay_s > 0:
        sleeper(nav_delay_s)

    progress_fn(f"  UI_Select (confirm {confirm_label})")
    trade_dispatch = controls.ui_select()
    if trade_dispatch.status != "ok":
        return RoutineResult(action="UI_Select", dispatch=trade_dispatch, details={"phase": "confirm"})

    # Wait for journal confirmation
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

    count = trade_event.get("Count", "?")
    cr_key = "TotalCost" if side == "buy" else "TotalSale"
    cr_val = trade_event.get(cr_key, "?")
    progress_fn(f"{event_type}: {count}x {target}, {cr_val} CR total")

    # Return to station menu
    back_dispatch = _market_back_out_to_station_menu(
        controls,
        step_delay_s=step_delay_s,
        sleeper=sleeper,
        progress_fn=progress_fn,
    )
    if back_dispatch.status != "ok":
        return RoutineResult(
            action="UI_Back",
            dispatch=back_dispatch,
            trigger_event=trade_event,
            details={"phase": "return_to_station_menu"},
        )
    if side == "sell":
        docked, reason = _is_currently_docked(market_path.parent)
        if not docked:
            return RoutineResult(
                action=event_type,
                dispatch=ActionDispatchResult(
                    action=event_type,
                    status="error",
                    reason=f"sell return-to-station check failed: {reason}",
                ),
                trigger_event=trade_event,
                details={"phase": "return_to_station_menu"},
            )

    return RoutineResult(
        action=event_type,
        dispatch=trade_dispatch,
        trigger_event=trade_event,
        details={"target": target, "amount": str(amount), "side": side},
    )
