"""
Market.json probe for Elite Dangerous macOS + CrossOver.

Reads the Market.json file Elite writes to the journal directory whenever
the player opens the commodities market screen in-game. Displays a formatted
table of all commodities with buy/sell prices, stock, and demand.

Open the market screen in-game first, then run this.

Usage:
    uv run python3 scratch_market.py --config config.toml
    uv run python3 scratch_market.py --config config.toml --filter gold
    uv run python3 scratch_market.py --config config.toml --sort buy
    uv run python3 scratch_market.py --config config.toml --sort alphabetical
    uv run python3 scratch_market.py --config config.toml --in-stock
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from edap.runtime import build_runtime_context, load_config_with_fallback

_BRACKET_LABEL = {0: "none", 1: "low", 2: "med", 3: "high"}


def _bracket(v: int) -> str:
    return _BRACKET_LABEL.get(v, str(v))


def _localised(item: dict, key: str) -> str:
    return item.get(f"{key}_Localised") or item.get(key, "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read and display Market.json from the ED journal directory")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--filter", metavar="TERM", help="case-insensitive substring filter on commodity name")
    parser.add_argument(
        "--sort",
        choices=["alphabetical", "buy", "sell", "stock", "demand", "category"],
        default=None,
        help="sort column (default: Market.json order)",
    )
    parser.add_argument("--in-stock", action="store_true", help="only show items with stock > 0")
    parser.add_argument("--wanted", action="store_true", help="only show items with demand > 0")
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

    term = args.filter.lower() if args.filter else None
    rows = []
    for item in items:
        name = _localised(item, "Name")
        category = _localised(item, "Category")
        buy = item.get("BuyPrice", 0)
        sell = item.get("SellPrice", 0)
        stock = item.get("Stock", 0)
        stock_bracket = item.get("StockBracket", 0)
        demand = item.get("Demand", 0)
        demand_bracket = item.get("DemandBracket", 0)

        if term and term not in name.lower() and term not in category.lower():
            continue
        if args.in_stock and stock == 0:
            continue
        if args.wanted and demand == 0:
            continue

        rows.append((name, category, buy, sell, stock, stock_bracket, demand, demand_bracket))

    if args.sort is not None:
        sort_key = {
            "alphabetical": lambda r: r[0].lower(),
            "category": lambda r: (r[1].lower(), r[0].lower()),
            "buy": lambda r: (-r[2], r[0].lower()),
            "sell": lambda r: (-r[3], r[0].lower()),
            "stock": lambda r: (-r[4], r[0].lower()),
            "demand": lambda r: (-r[6], r[0].lower()),
        }[args.sort]
        rows.sort(key=sort_key)

    if not rows:
        print("No items match the current filters.")
        return

    col_name = max(len(r[0]) for r in rows)
    col_cat = max(len(r[1]) for r in rows)
    col_name = max(col_name, 10)
    col_cat = max(col_cat, 8)

    header = (
        f"{'Commodity':<{col_name}}  {'Category':<{col_cat}}"
        f"  {'Buy':>8}  {'Sell':>8}  {'Stock':>8}  {'Stk':>4}  {'Demand':>8}  {'Dem':>4}"
    )
    print(header)
    print("-" * len(header))

    for name, category, buy, sell, stock, sb, demand, db in rows:
        buy_s = f"{buy:,}" if buy > 0 else "-"
        sell_s = f"{sell:,}" if sell > 0 else "-"
        stock_s = f"{stock:,}" if stock > 0 else "-"
        demand_s = f"{demand:,}" if demand > 0 else "-"
        print(
            f"{name:<{col_name}}  {category:<{col_cat}}"
            f"  {buy_s:>8}  {sell_s:>8}  {stock_s:>8}  {_bracket(sb):>4}  {demand_s:>8}  {_bracket(db):>4}"
        )

    print()
    print(f"{len(rows)} item(s) shown")


if __name__ == "__main__":
    main()
