from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from edap.routines.haul_two_way import Phase, haul_loop_two_way
from edap.routines._base import ActionDispatchResult, RoutineResult
from tests.fakes import FakeShipControls, FakeWatcher

_STATION_1 = "Pawelczyk Dock"
_STATION_2 = "Trevithick Dock"
_SYSTEM_1 = "Sol"
_SYSTEM_2 = "Achenar"
_CARGO_1 = "Aluminium"
_CARGO_2 = "Bertrandite"


def _ticking_clock(step: float = 0.01):
    t = [0.0]

    def fn() -> float:
        value = t[0]
        t[0] += step
        return value

    return fn


def _write_market(journal_dir: Path, station_name: str, items: list[dict]) -> None:
    (journal_dir / "Market.json").write_text(
        json.dumps({"StationName": station_name, "Items": items}),
        encoding="utf-8",
    )


class TwoWayHaulLoopTests(unittest.TestCase):
    def test_one_iteration_happy_path(self) -> None:
        controls = FakeShipControls()
        market_calls: list[tuple[str, str]] = []
        watcher = FakeWatcher([
            [],
            [{"event": "Undocked", "StationName": _STATION_1}],
            [{"event": "Music", "MusicTrack": "NoTrack"}],
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION_2}],
            [{"event": "Docked", "StationName": _STATION_2}],
            [],
            [{"event": "Undocked", "StationName": _STATION_2}],
            [{"event": "Music", "MusicTrack": "NoTrack"}],
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION_1}],
            [{"event": "Docked", "StationName": _STATION_1}],
        ])

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            _write_market(
                journal_dir,
                _STATION_1,
                [
                    {"Category": "Metals", "Name": "aluminium", "Name_Localised": _CARGO_1, "DemandBracket": 1, "Stock": 1000},
                    {"Category": "Minerals", "Name": "bertrandite", "Name_Localised": _CARGO_2, "DemandBracket": 1, "Stock": 1000},
                ],
            )
            with patch("edap.routines.haul_two_way.market_sell") as market_sell_mock, patch(
                "edap.routines.haul_two_way.market_buy"
            ) as market_buy_mock:
                market_sell_mock.side_effect = lambda controls, watcher, **kwargs: (
                    market_calls.append(("sell", kwargs["target"])) or RoutineResult(
                        action="market_sell",
                        dispatch=ActionDispatchResult(action="market_sell", status="ok"),
                    )
                )
                market_buy_mock.side_effect = lambda controls, watcher, **kwargs: (
                    market_calls.append(("buy", kwargs["target"])) or RoutineResult(
                        action="market_buy",
                        dispatch=ActionDispatchResult(action="market_buy", status="ok"),
                    )
                )
                result = haul_loop_two_way(
                    controls,
                    watcher,
                    journal_dir=journal_dir,
                    station_1=_STATION_1,
                    station_1_buying=_CARGO_1,
                    station_1_system=_SYSTEM_1,
                    station_2=_STATION_2,
                    station_2_buying=_CARGO_2,
                    station_2_system=_SYSTEM_2,
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
        self.assertEqual(
            market_calls,
            [
                ("sell", _CARGO_2),
                ("buy", _CARGO_1),
                ("sell", _CARGO_1),
                ("buy", _CARGO_2),
            ],
        )
        self.assertEqual(
            [call["action"] for call in controls.calls if call["action"] in {"SetSpeed100", "UseBoostJuice"}].count("SetSpeed100"),
            2,
        )

    def test_can_start_from_station_2_phase(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION_1}],
            [{"event": "Docked", "StationName": _STATION_1}],
        ])

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            _write_market(
                journal_dir,
                _STATION_2,
                [
                    {"Category": "Metals", "Name": "aluminium", "Name_Localised": _CARGO_1, "DemandBracket": 1, "Stock": 1000},
                    {"Category": "Minerals", "Name": "bertrandite", "Name_Localised": _CARGO_2, "DemandBracket": 1, "Stock": 1000},
                ],
            )
            result = haul_loop_two_way(
                controls,
                watcher,
                journal_dir=journal_dir,
                station_1=_STATION_1,
                station_1_buying=_CARGO_1,
                station_1_system=_SYSTEM_1,
                station_2=_STATION_2,
                station_2_buying=_CARGO_2,
                station_2_system=_SYSTEM_2,
                iterations=1,
                start_phase=Phase.DEPART_STATION_2_SYSTEM,
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

    def test_rejects_duplicate_stations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "station_1 and station_2 must differ"):
                haul_loop_two_way(
                    FakeShipControls(),
                    FakeWatcher([]),
                    journal_dir=Path(tmp),
                    station_1=_STATION_1,
                    station_1_buying=_CARGO_1,
                    station_2=_STATION_1,
                    station_2_buying=_CARGO_2,
                )


if __name__ == "__main__":
    unittest.main()
