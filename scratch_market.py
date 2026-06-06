"""
Market.json probe for Elite Dangerous macOS + CrossOver.

Reads the Market.json file Elite writes to the journal directory whenever
the player opens the commodities market screen in-game.

Default display mirrors the in-game layout: BUY section (items with stock)
then SELL section (items with demand), each grouped by category alphabetically
with items sorted alphabetically within each category.

Open the market screen in-game first, then run this.

Usage:
    uv run python3 scratch_market.py --config config.toml
    uv run python3 scratch_market.py --config config.toml --filter gold
    uv run python3 scratch_market.py --config config.toml --raw
    uv run python3 scratch_market.py --config config.toml --raw --sort sell
"""
from __future__ import annotations

import argparse
import json
import sys

from edap.runtime import build_runtime_context, load_config_with_fallback

_BRACKET_LABEL = {0: "none", 1: "low", 2: "med", 3: "high"}


def _bracket(v: int) -> str:
    return _BRACKET_LABEL.get(v, str(v))


def _localised(item: dict, key: str) -> str:
    return item.get(f"{key}_Localised") or item.get(key, "")


def _ingame_display(items: list[dict], filter_term: str | None) -> None:
    term = filter_term.lower() if filter_term else None

    buy_groups: dict[str, list[tuple[str, int, int]]] = {}
    sell_groups: dict[str, list[tuple[str, int, int]]] = {}

    for item in items:
        name = _localised(item, "Name")
        category = _localised(item, "Category")
        if term and term not in name.lower() and term not in category.lower():
            continue
        stock = item.get("Stock", 0)
        demand = item.get("Demand", 0)
        if stock > 0:
            buy_groups.setdefault(category, []).append((name, stock, item.get("BuyPrice", 0)))
        if item.get("DemandBracket", 0) > 0:
            sell_groups.setdefault(category, []).append((name, demand, item.get("SellPrice", 0)))

    all_names = [n for grp in (buy_groups, sell_groups) for it in grp.values() for n, _, _ in it]
    col = max((len(n) for n in all_names), default=10)
    col = max(col, 10)

    def _render(title: str, groups: dict, value_hdr: str, price_hdr: str) -> list[str]:
        lines = [title, f"  {'GOODS':<{col}}  {value_hdr:>10}  {price_hdr:>10}", f"  {'─' * (col + 26)}"]
        if not groups:
            lines.append("  (none)")
        else:
            for cat in sorted(groups):
                lines.append(f"  {cat}")
                for name, value, price in sorted(groups[cat], key=lambda r: r[0].lower()):
                    lines.append(f"    {name:<{col}}  {value:>10,}  {price:>8,} CR")
        return lines

    buy_lines = _render("BUY FROM MARKET", buy_groups, "SUPPLY", "BUY")
    sell_lines = _render("SELL TO MARKET", sell_groups, "DEMAND", "SELL")

    left_w = max((len(l) for l in buy_lines), default=0)
    for i in range(max(len(buy_lines), len(sell_lines))):
        left = buy_lines[i] if i < len(buy_lines) else ""
        right = sell_lines[i] if i < len(sell_lines) else ""
        print(f"{left:<{left_w}}  │  {right}")


def _raw_display(items: list[dict], filter_term: str | None, sort: str | None) -> None:
    term = filter_term.lower() if filter_term else None
    rows = []
    for item in items:
        name = _localised(item, "Name")
        category = _localised(item, "Category")
        if term and term not in name.lower() and term not in category.lower():
            continue
        rows.append((
            name, category,
            item.get("BuyPrice", 0), item.get("SellPrice", 0),
            item.get("Stock", 0), item.get("StockBracket", 0),
            item.get("Demand", 0), item.get("DemandBracket", 0),
        ))

    if sort is not None:
        key = {
            "alphabetical": lambda r: r[0].lower(),
            "category": lambda r: (r[1].lower(), r[0].lower()),
            "buy": lambda r: (-r[2], r[0].lower()),
            "sell": lambda r: (-r[3], r[0].lower()),
            "stock": lambda r: (-r[4], r[0].lower()),
            "demand": lambda r: (-r[6], r[0].lower()),
        }[sort]
        rows.sort(key=key)

    if not rows:
        print("No items match.")
        return

    col_name = max((len(r[0]) for r in rows), default=10)
    col_cat = max((len(r[1]) for r in rows), default=8)
    col_name = max(col_name, 10)
    col_cat = max(col_cat, 8)

    hdr = (
        f"{'Commodity':<{col_name}}  {'Category':<{col_cat}}"
        f"  {'Buy':>8}  {'Sell':>8}  {'Stock':>8}  {'Stk':>4}  {'Demand':>8}  {'Dem':>4}"
    )
    print(hdr)
    print("-" * len(hdr))
    for name, cat, buy, sell, stock, sb, demand, db in rows:
        print(
            f"{name:<{col_name}}  {cat:<{col_cat}}"
            f"  {buy:>8,}  {sell:>8,}  {stock:>8,}  {_bracket(sb):>4}  {demand:>8,}  {_bracket(db):>4}"
        )
    print(f"\n{len(rows)} item(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read and display Market.json from the ED journal directory")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--filter", metavar="TERM", help="case-insensitive substring filter on name or category")
    parser.add_argument("--raw", action="store_true", help="flat table of all items instead of in-game layout")
    parser.add_argument(
        "--sort",
        choices=["alphabetical", "category", "buy", "sell", "stock", "demand"],
        default=None,
        help="sort for --raw mode (default: Market.json order)",
    )
    args = parser.parse_args()

    loaded = load_config_with_fallback(args.config)
    ctx = build_runtime_context(loaded.config)
    journal_dir = ctx.journal.effective_path
    if journal_dir is None:
        print(
            f"ERROR: could not resolve journal directory "
            f"(source: {ctx.journal.cli_source_status()}). "
            "Set paths.journal_dir in config.toml or ensure CrossOver auto-detection works.",
            file=sys.stderr,
        )
        sys.exit(1)

    market_path = journal_dir / "Market.json"
    if not market_path.exists():
        print(f"ERROR: Market.json not found at {market_path}", file=sys.stderr)
        print("Open the commodities market screen in-game first, then re-run.", file=sys.stderr)
        sys.exit(1)

    with market_path.open() as fh:
        data = json.load(fh)

    station = data.get("StationName", "?")
    system = data.get("StarSystem", "?")
    market_id = data.get("MarketID", "?")
    ts = data.get("timestamp", "?")
    items: list[dict] = data.get("Items", [])

    print(f"Station:   {station}  ({system})")
    print(f"MarketID:  {market_id}")
    print(f"Timestamp: {ts}")
    print(f"Items:     {len(items)}")
    print()

    if args.raw:
        _raw_display(items, args.filter, args.sort)
    else:
        _ingame_display(items, args.filter)


if __name__ == "__main__":
    main()
