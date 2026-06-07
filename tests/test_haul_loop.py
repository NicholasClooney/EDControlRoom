from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from edap.routines import haul_loop
from edap.routines.haul import Phase, _detect_phase
from tests.fakes import FakeShipControls, FakeWatcher

_STATION = "Pawelczyk Dock"
_BUY_STATION = "Trevithick Dock"
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


def _write_journal(journal_dir: Path, events: list[dict], filename: str = "Journal.240101000000.01.log") -> None:
    path = journal_dir / filename
    lines = "\n".join(json.dumps(e) for e in events) + "\n"
    path.write_text(lines, encoding="utf-8")


def _write_cargo(journal_dir: Path, items: list[dict]) -> None:
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
            # Phase 3: dock at buy station (wait_for_supercruise_exit=True, auto_refuel=True)
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],   # absorbed by dock's prime watcher.poll() after boost
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION}],
            [{"event": "Docked", "StationName": _STATION}],
            # buy-station station_refuel_menu_sequence runs after Docked — no events needed
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
                sell_station=_STATION,
                confirm_fn=lambda _: False,
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
        boost_calls = [c for c in controls.calls if c["action"] == "UseBoostJuice"]
        self.assertEqual(len(boost_calls), 2)
        # HeadLookReset appears once per undock call (2 undocks total)
        head_look_calls = [c for c in controls.calls if c["action"] == "HeadLookReset"]
        self.assertEqual(len(head_look_calls), 2)
        # Refuel menu sequence (UI_Up, UI_Select, UI_Down) now runs at both stations after Docked
        up_calls = [c for c in controls.calls if c["action"] == "UI_Up"]
        self.assertEqual(len(up_calls), 2)

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
                sell_station=_STATION,
                confirm_fn=lambda _: False,
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
                sell_station=_STATION,
                confirm_fn=lambda _: False,
                iterations=1,
                step_delay_s=0.0,
                undock_timeout_s=10.0,
                dock_timeout_s=0.0,   # expires immediately
                time_fn=_ticking_clock(step=0.1),
                sleeper=lambda _: None,
            )

        self.assertEqual(result.dispatch.status, "error")
        self.assertIn("supercruise", result.dispatch.reason.lower())


class DetectPhaseTests(unittest.TestCase):
    """Tests for _detect_phase journal/cargo-based phase detection."""

    def _call(self, journal_dir: Path, *, sell_station: str = _STATION, buy_station: str = _BUY_STATION,
              sell_system: str = "", buy_system: str = "", commodity: str = _COMMODITY,
              confirm_fn=None) -> tuple[Phase, str]:
        return _detect_phase(
            journal_dir,
            sell_station=sell_station,
            buy_station=buy_station,
            sell_system=sell_system,
            buy_system=buy_system,
            commodity=commodity,
            confirm_fn=confirm_fn or (lambda _: False),
        )

    def test_docked_at_sell_with_target_cargo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_journal(d, [{"event": "Docked", "StationName": _STATION, "StarSystem": "Sol"}])
            _write_cargo(d, [{"Name": _COMMODITY_LOWER, "Count": 100}])
            phase, _ = self._call(d)
        self.assertEqual(phase, Phase.SELL)

    def test_docked_at_sell_empty_hold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_journal(d, [{"event": "Docked", "StationName": _STATION, "StarSystem": "Sol"}])
            _write_cargo(d, [])
            phase, _ = self._call(d)
        self.assertEqual(phase, Phase.UNDOCK_SELL)

    def test_docked_at_buy_empty_hold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_journal(d, [{"event": "Docked", "StationName": _BUY_STATION, "StarSystem": "Alpha"}])
            _write_cargo(d, [])
            phase, _ = self._call(d)
        self.assertEqual(phase, Phase.BUY)

    def test_docked_at_buy_with_target_cargo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_journal(d, [{"event": "Docked", "StationName": _BUY_STATION, "StarSystem": "Alpha"}])
            _write_cargo(d, [{"Name": _COMMODITY_LOWER, "Count": 100}])
            phase, _ = self._call(d)
        self.assertEqual(phase, Phase.UNDOCK_BUY)

    def test_not_docked_with_target_cargo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_journal(d, [{"event": "SupercruiseExit", "StarSystem": "Sol"}])
            _write_cargo(d, [{"Name": _COMMODITY_LOWER, "Count": 100}])
            phase, _ = self._call(d)
        self.assertEqual(phase, Phase.TRANSIT_TO_SELL)

    def test_not_docked_empty_hold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_journal(d, [{"event": "SupercruiseEntry", "StarSystem": "Alpha"}])
            _write_cargo(d, [])
            phase, _ = self._call(d)
        self.assertEqual(phase, Phase.TRANSIT_TO_BUY)

    def test_auto_fill_buy_station_confirm_true(self) -> None:
        """Docked at unknown station with buy_station='', confirm=True -> updated buy_station."""
        unknown = "Mystery Base"
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_journal(d, [{"event": "Docked", "StationName": unknown, "StarSystem": "Far"}])
            _write_cargo(d, [])
            phase, updated_buy = _detect_phase(
                d,
                sell_station=_STATION,
                buy_station="",
                sell_system="",
                buy_system="",
                commodity=_COMMODITY,
                confirm_fn=lambda _: True,
            )
        self.assertEqual(phase, Phase.BUY)
        self.assertEqual(updated_buy, unknown)

    def test_auto_fill_buy_station_confirm_false_raises(self) -> None:
        """confirm_fn=False raises RuntimeError."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_journal(d, [{"event": "Docked", "StationName": "Mystery Base", "StarSystem": "Far"}])
            _write_cargo(d, [])
            with self.assertRaises(RuntimeError):
                _detect_phase(
                    d,
                    sell_station=_STATION,
                    buy_station="",
                    sell_system="",
                    buy_system="",
                    commodity=_COMMODITY,
                    confirm_fn=lambda _: False,
                )

    def test_docked_at_fully_unknown_station_raises(self) -> None:
        """Docked at unknown station when both stations are configured raises RuntimeError."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_journal(d, [{"event": "Docked", "StationName": "Alien Station", "StarSystem": "Weird"}])
            _write_cargo(d, [])
            with self.assertRaises(RuntimeError):
                self._call(d)

    def test_matching_sell_station_raises_on_collision(self) -> None:
        """sell_station == buy_station raises RuntimeError."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_journal(d, [{"event": "Docked", "StationName": _STATION, "StarSystem": "Sol"}])
            _write_cargo(d, [])
            with self.assertRaises(RuntimeError):
                self._call(d, buy_station=_STATION)

    def test_empty_commodity_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_journal(d, [{"event": "Docked", "StationName": _STATION, "StarSystem": "Sol"}])
            _write_cargo(d, [])
            with self.assertRaises(RuntimeError):
                self._call(d, commodity="")


class DetectPhaseResumeIntegrationTest(unittest.TestCase):
    """haul_loop resumes from a non-SELL phase detected via journal state."""

    def test_resume_from_buy_phase(self) -> None:
        """Seed journal as 'docked at buy station, empty hold' -> loop starts at BUY."""
        controls = FakeShipControls()
        watcher = FakeWatcher([
            # Phase 4: market_buy
            [{"event": "MarketBuy", "Type": _COMMODITY_LOWER, "Type_Localised": _COMMODITY, "Count": 100, "TotalCost": 100_000}],
            # Phase 5: undock from buy
            [],
            [{"event": "Undocked", "StationName": _BUY_STATION}],
            # Phase 6: transit to sell + dock
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION}],
            [{"event": "Docked", "StationName": _STATION}],
        ])

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            # Journal says docked at buy station
            _write_journal(d, [{"event": "Docked", "StationName": _BUY_STATION, "StarSystem": "Alpha"}])
            # Empty hold -> should detect BUY phase
            _write_cargo(d, [])
            # Market.json for buy
            (d / "Market.json").write_text(
                json.dumps({
                    "StationName": _BUY_STATION,
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

            result = haul_loop(
                controls,
                watcher,
                journal_dir=d,
                commodity=_COMMODITY,
                sell_station=_STATION,
                buy_station=_BUY_STATION,
                confirm_fn=lambda _: False,
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
        # Only one boost (one dock call — TRANSIT_TO_SELL)
        boost_calls = [c for c in controls.calls if c["action"] == "UseBoostJuice"]
        self.assertEqual(len(boost_calls), 1)


class SellPhaseNarrowedToTargetTest(unittest.TestCase):
    """Phase 1 sells only the target commodity; non-target cargo is left alone."""

    def test_only_target_sold_non_target_stays(self) -> None:
        messages: list[str] = []

        controls = FakeShipControls()
        watcher = FakeWatcher([
            # Phase 1: MarketSell for Aluminium only
            [{"event": "MarketSell", "Type": _COMMODITY_LOWER, "Type_Localised": _COMMODITY, "Count": 100, "TotalSale": 50_000}],
            # Phase 2: undock
            [],
            [{"event": "Undocked", "StationName": _STATION}],
            # Phase 3: transit to buy + dock
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION}],
            [{"event": "Docked", "StationName": _STATION}],
            # Phase 4: buy
            [{"event": "MarketBuy", "Type": _COMMODITY_LOWER, "Type_Localised": _COMMODITY, "Count": 100, "TotalCost": 50_000}],
            # Phase 5: undock
            [],
            [{"event": "Undocked", "StationName": _STATION}],
            # Phase 6: transit to sell + dock
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION}],
            [{"event": "Docked", "StationName": _STATION}],
        ])

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_fixtures(
                d,
                cargo_items=[
                    {"Name": _COMMODITY_LOWER, "Name_Localised": _COMMODITY, "Count": 100},
                    {"Name": "gold", "Name_Localised": "Gold", "Count": 5},
                ],
                market_station=_STATION,
            )

            result = haul_loop(
                controls,
                watcher,
                journal_dir=d,
                commodity=_COMMODITY,
                sell_station=_STATION,
                confirm_fn=lambda _: False,
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
                progress_fn=messages.append,
            )

        self.assertEqual(result.dispatch.status, "ok")

        # Only one MarketSell attempted (Aluminium), not Gold
        sell_targets = [
            msg for msg in messages
            if msg.strip().startswith("Selling") and "Selling cargo" not in msg
        ]
        # Verify Gold was NOT sold — no "Selling Gold" message
        self.assertFalse(any("Gold" in m and "Selling" in m and "non-target" not in m for m in sell_targets))

        # INFO line about non-target cargo should be emitted
        non_target_messages = [m for m in messages if "non-target" in m.lower()]
        self.assertTrue(len(non_target_messages) >= 1, f"Expected non-target info line, got: {messages}")
        self.assertIn("Gold", non_target_messages[0])
