from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from edap.routines import haul_loop
from tests.fakes import FakeShipControls, FakeWatcher

_STATION = "Pawelczyk Dock"
_COMMODITY = "Aluminium"
_COMMODITY_LOWER = "aluminium"


def _ticking_clock(step: float = 0.01):
    t = [0.0]

    def fn() -> float:
        v = t[0]
        t[0] += step
        return v

    return fn


def _write_fixtures(
    journal_dir: Path,
    *,
    cargo_items: list[dict] | None = None,
    market_station: str = _STATION,
) -> None:
    # Journal file so market station-check can find a matching Docked event
    journal_file = journal_dir / "Journal.240101000000.01.log"
    journal_file.write_text(
        json.dumps({"timestamp": "2024-01-01T00:00:00Z", "event": "Docked", "StationName": market_station}) + "\n",
        encoding="utf-8",
    )

    # Market.json: Aluminium buyable (Stock > 0) and sellable (DemandBracket > 0)
    (journal_dir / "Market.json").write_text(
        json.dumps({
            "StationName": market_station,
            "Items": [
                {
                    "Category": "Metals",
                    "Name": _COMMODITY_LOWER,
                    "Name_Localised": _COMMODITY,
                    "DemandBracket": 1,
                    "Stock": 1000,
                }
            ],
        }),
        encoding="utf-8",
    )

    items = cargo_items if cargo_items is not None else [
        {"Name": _COMMODITY_LOWER, "Name_Localised": _COMMODITY, "Count": 100}
    ]
    (journal_dir / "Cargo.json").write_text(
        json.dumps({"Inventory": items}),
        encoding="utf-8",
    )


class HaulLoopTests(unittest.TestCase):
    def test_one_iteration_happy_path(self) -> None:
        """Full 6-phase haul loop completes successfully with real routines and fake dependencies."""
        controls = FakeShipControls()
        watcher = FakeWatcher([
            # Phase 1: market_sell — event returned from prime poll (pending_events)
            [{"event": "MarketSell", "Type": _COMMODITY_LOWER, "Type_Localised": _COMMODITY, "Count": 100, "TotalSale": 100_000}],
            # Phase 2: undock from sell station
            [],   # absorbed by undock's prime watcher.poll()
            [{"event": "Undocked", "StationName": _STATION}],
            # Phase 3: dock at buy station (wait_for_supercruise_exit=True)
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],   # absorbed by dock's prime watcher.poll() after boost
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION}],
            [{"event": "Docked", "StationName": _STATION}],
            # Phase 4: market_buy — event returned from prime poll (pending_events)
            [{"event": "MarketBuy", "Type": _COMMODITY_LOWER, "Type_Localised": _COMMODITY, "Count": 100, "TotalCost": 100_000}],
            # Phase 5: undock from buy station
            [],   # absorbed by undock's prime watcher.poll()
            [{"event": "Undocked", "StationName": _STATION}],
            # Phase 6: dock at sell station (wait_for_supercruise_exit=True, auto_refuel=True)
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],   # absorbed by dock's prime watcher.poll() after boost
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION}],
            [{"event": "Docked", "StationName": _STATION}],
            # station_refuel_menu_sequence runs after Docked — no events needed
        ])

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            _write_fixtures(journal_dir)

            result = haul_loop(
                controls,
                watcher,
                journal_dir=journal_dir,
                commodity=_COMMODITY,
                iterations=1,
                step_delay_s=0.0,
                settle_s=0.0,
                boost_settle_s=0.0,
                dock_timeout_s=30.0,
                request_timeout_s=10.0,
                undock_timeout_s=10.0,
                trade_timeout_s=10.0,
                time_fn=_ticking_clock(),
                sleeper=lambda _: None,
            )

        self.assertEqual(result.dispatch.status, "ok")
        # Boost should appear once per dock call (2 docks total)
        boost_calls = [c for c in controls.calls if c["action"] == "BoostButton"]
        self.assertEqual(len(boost_calls), 2)
        # HeadLookReset appears once per undock call (2 undocks total)
        head_look_calls = [c for c in controls.calls if c["action"] == "HeadLookReset"]
        self.assertEqual(len(head_look_calls), 2)

    def test_aborts_when_undock_fails(self) -> None:
        """haul_loop returns an error result immediately when undock times out."""
        controls = FakeShipControls()
        watcher = FakeWatcher([
            [],  # absorbed by undock's prime watcher.poll() — no Undocked event follows
        ])

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            _write_fixtures(journal_dir, cargo_items=[])  # no cargo — skip sell phase

            result = haul_loop(
                controls,
                watcher,
                journal_dir=journal_dir,
                commodity=_COMMODITY,
                iterations=1,
                step_delay_s=0.0,
                undock_timeout_s=0.0,  # expires immediately
                time_fn=_ticking_clock(step=0.1),
                sleeper=lambda _: None,
            )

        self.assertEqual(result.dispatch.status, "error")
        self.assertIn("Undocked", result.dispatch.reason)

    def test_aborts_when_dock_at_buy_station_fails(self) -> None:
        """haul_loop returns an error result when dock at buy station times out waiting for SupercruiseExit."""
        controls = FakeShipControls()
        watcher = FakeWatcher([
            # Phase 1: market_sell (no cargo — skipped)
            # Phase 2: undock succeeds
            [],
            [{"event": "Undocked", "StationName": _STATION}],
            # Phase 3: dock at buy — SupercruiseExit never arrives
        ])

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            _write_fixtures(journal_dir, cargo_items=[])

            result = haul_loop(
                controls,
                watcher,
                journal_dir=journal_dir,
                commodity=_COMMODITY,
                iterations=1,
                step_delay_s=0.0,
                undock_timeout_s=10.0,
                dock_timeout_s=0.0,   # expires immediately
                time_fn=_ticking_clock(step=0.1),
                sleeper=lambda _: None,
            )

        self.assertEqual(result.dispatch.status, "error")
        self.assertIn("supercruise", result.dispatch.reason.lower())
