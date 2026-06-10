from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from edap.routines._callbacks import noop_announce, noop_progress
from edap.routines.haul_two_way import Phase, StationLeg, _detect_start_phase, haul_loop_two_way as _haul_loop_two_way
from edap.routines._base import ActionDispatchResult, RoutineResult
from edap.tts import AnnouncementId
from tests.fakes import FakeShipControls, FakeWatcher

_STATION_1 = "Pawelczyk Dock"
_STATION_2 = "Trevithick Dock"
_SYSTEM_1 = "Sol"
_SYSTEM_2 = "Achenar"
_CARGO_1 = "Aluminium"
_CARGO_2 = "Bertrandite"


def haul_loop_two_way(*args, **kwargs):
    kwargs.setdefault("progress_fn", noop_progress)
    kwargs.setdefault("announce_fn", noop_announce)
    return _haul_loop_two_way(*args, **kwargs)


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


def _write_cargo(journal_dir: Path, inventory: list[dict]) -> None:
    (journal_dir / "Cargo.json").write_text(
        json.dumps({"Inventory": inventory}),
        encoding="utf-8",
    )


def _write_journal(journal_dir: Path, *events: dict[str, object]) -> None:
    lines = "\n".join(json.dumps(event) for event in events)
    (journal_dir / "Journal.240101000000.01.log").write_text(f"{lines}\n", encoding="utf-8")


def _station_1_leg() -> StationLeg:
    return StationLeg(index=1, station=_STATION_1, system=_SYSTEM_1, buy_commodity=_CARGO_1, sell_commodity=_CARGO_2)


def _station_2_leg() -> StationLeg:
    return StationLeg(index=2, station=_STATION_2, system=_SYSTEM_2, buy_commodity=_CARGO_2, sell_commodity=_CARGO_1)


class TwoWayHaulLoopTests(unittest.TestCase):
    def test_detect_start_phase_docked_at_station_1_with_full_station_1_cargo_undocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            _write_journal(
                journal_dir,
                {
                    "event": "Docked",
                    "StationName": _STATION_1,
                    "StarSystem": _SYSTEM_1,
                    "CargoCapacity": 64,
                },
            )
            _write_cargo(journal_dir, [{"Name": "aluminium", "Count": 64, "Stolen": 0}])

            phase = _detect_start_phase(
                journal_dir,
                station_1=_station_1_leg(),
                station_2=_station_2_leg(),
                progress_fn=noop_progress,
            )

        self.assertEqual(phase, Phase.UNDOCK_STATION_1)

    def test_detect_start_phase_docked_at_station_2_with_full_station_2_cargo_undocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            _write_journal(
                journal_dir,
                {
                    "event": "Docked",
                    "StationName": _STATION_2,
                    "StarSystem": _SYSTEM_2,
                    "CargoCapacity": 64,
                },
            )
            _write_cargo(journal_dir, [{"Name": "bertrandite", "Count": 64, "Stolen": 0}])

            phase = _detect_start_phase(
                journal_dir,
                station_1=_station_1_leg(),
                station_2=_station_2_leg(),
                progress_fn=noop_progress,
            )

        self.assertEqual(phase, Phase.UNDOCK_STATION_2)

    def test_detect_start_phase_docked_at_station_1_with_partial_station_1_cargo_stays_in_buy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            _write_journal(
                journal_dir,
                {
                    "event": "Docked",
                    "StationName": _STATION_1,
                    "StarSystem": _SYSTEM_1,
                    "CargoCapacity": 64,
                },
            )
            _write_cargo(journal_dir, [{"Name": "aluminium", "Count": 20, "Stolen": 0}])

            phase = _detect_start_phase(
                journal_dir,
                station_1=_station_1_leg(),
                station_2=_station_2_leg(),
                progress_fn=noop_progress,
            )

        self.assertEqual(phase, Phase.AT_STATION_1_BUY)

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
            _write_cargo(
                journal_dir,
                [{"Name": "bertrandite", "Count": 64, "Stolen": 0}],
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
                    supercruise_exit_settle_s=0.0,
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

    def test_stop_requested_halts_at_station_1_sale_boundary_before_buy(self) -> None:
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
            _write_cargo(
                journal_dir,
                [{"Name": "bertrandite", "Count": 64, "Stolen": 0}],
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
                    step_delay_s=0.0,
                    settle_s=0.0,
                    supercruise_exit_settle_s=0.0,
                    boost_settle_s=0.0,
                    dock_timeout_s=30.0,
                    request_timeout_s=10.0,
                    undock_timeout_s=10.0,
                    trade_timeout_s=10.0,
                    time_fn=_ticking_clock(),
                    sleeper=lambda _: None,
                    stop_requested_fn=lambda: True,
                )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(
            market_calls,
            [
                ("sell", _CARGO_2),
            ],
        )

    def test_stop_requested_halts_immediately_when_resumed_at_station_1_buy(self) -> None:
        controls = FakeShipControls()
        market_calls: list[tuple[str, str]] = []
        watcher = FakeWatcher([])

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            _write_journal(
                journal_dir,
                {
                    "event": "Docked",
                    "StationName": _STATION_1,
                    "StarSystem": _SYSTEM_1,
                    "CargoCapacity": 64,
                },
            )
            _write_cargo(journal_dir, [{"Name": "aluminium", "Count": 20, "Stolen": 0}])
            _write_market(
                journal_dir,
                _STATION_1,
                [
                    {"Category": "Metals", "Name": "aluminium", "Name_Localised": _CARGO_1, "DemandBracket": 1, "Stock": 1000},
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
                    step_delay_s=0.0,
                    settle_s=0.0,
                    supercruise_exit_settle_s=0.0,
                    boost_settle_s=0.0,
                    dock_timeout_s=30.0,
                    request_timeout_s=10.0,
                    undock_timeout_s=10.0,
                    trade_timeout_s=10.0,
                    time_fn=_ticking_clock(),
                    sleeper=lambda _: None,
                    stop_requested_fn=lambda: True,
                )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(market_calls, [])

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
        raw_k_calls = [call for call in controls.calls if call["action"] == "raw:k"]
        self.assertEqual(len(raw_k_calls), 1)

    def test_departure_engages_raw_k_after_mass_lock_clears_by_default(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([])

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
            _write_cargo(journal_dir, [])
            (journal_dir / "Status.json").write_text(json.dumps({"Flags": 0}), encoding="utf-8")

            with patch("edap.routines.haul_two_way.dock") as dock_mock:
                dock_mock.return_value = RoutineResult(
                    action="dock",
                    dispatch=ActionDispatchResult(action="dock", status="error", reason="stop after first transit"),
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
                    start_phase=Phase.DEPART_STATION_1_SYSTEM,
                    step_delay_s=0.0,
                    settle_s=0.0,
                    supercruise_exit_settle_s=0.0,
                    boost_settle_s=0.0,
                    dock_timeout_s=30.0,
                    request_timeout_s=10.0,
                    undock_timeout_s=10.0,
                    trade_timeout_s=10.0,
                    time_fn=_ticking_clock(),
                    sleeper=lambda _: None,
                )

        self.assertEqual(result.dispatch.status, "error")
        actions = [call["action"] for call in controls.calls]
        self.assertIn("raw:k", actions)
        self.assertLess(actions.index("SetSpeed100"), actions.index("raw:k"))

    def test_departure_skips_raw_k_when_auto_hyperspace_disabled(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([])

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
            _write_cargo(journal_dir, [])
            (journal_dir / "Status.json").write_text(json.dumps({"Flags": 0}), encoding="utf-8")

            with patch("edap.routines.haul_two_way.dock") as dock_mock:
                dock_mock.return_value = RoutineResult(
                    action="dock",
                    dispatch=ActionDispatchResult(action="dock", status="error", reason="stop after first transit"),
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
                    start_phase=Phase.DEPART_STATION_1_SYSTEM,
                    step_delay_s=0.0,
                    settle_s=0.0,
                    boost_settle_s=0.0,
                    dock_timeout_s=30.0,
                    request_timeout_s=10.0,
                    undock_timeout_s=10.0,
                    trade_timeout_s=10.0,
                    auto_hyperspace_engage=False,
                    time_fn=_ticking_clock(),
                    sleeper=lambda _: None,
                )

        self.assertEqual(result.dispatch.status, "error")
        self.assertNotIn("raw:k", [call["action"] for call in controls.calls])

    def test_transit_opens_nav_panel_after_hyperspace_arrival_by_default(self) -> None:
        controls = FakeShipControls()
        sleep_calls: list[float] = []
        watcher = FakeWatcher([
            [{"event": "FSDJump", "StarSystem": _SYSTEM_2}],
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION_2}],
            [{"event": "Docked", "StationName": _STATION_2}],
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
            _write_cargo(journal_dir, [])
            with patch("edap.routines.haul_two_way.market_sell") as market_sell_mock:
                market_sell_mock.return_value = RoutineResult(
                    action="market_sell",
                    dispatch=ActionDispatchResult(action="market_sell", status="error", reason="stop after transit"),
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
                    start_phase=Phase.TRANSIT_TO_STATION_2,
                    step_delay_s=0.0,
                    settle_s=0.0,
                    supercruise_exit_settle_s=0.0,
                    boost_settle_s=0.0,
                    dock_timeout_s=30.0,
                    request_timeout_s=10.0,
                    undock_timeout_s=10.0,
                    trade_timeout_s=10.0,
                    time_fn=_ticking_clock(),
                    sleeper=lambda s: sleep_calls.append(s),
                )

        self.assertEqual(result.dispatch.status, "error")
        actions = [call["action"] for call in controls.calls]
        self.assertEqual(actions.count("FocusLeftPanel"), 2)
        self.assertLess(actions.index("FocusLeftPanel"), actions.index("UseBoostJuice"))
        self.assertIn(3.0, sleep_calls)

    def test_transit_skips_nav_panel_when_disabled(self) -> None:
        controls = FakeShipControls()
        sleep_calls: list[float] = []
        watcher = FakeWatcher([
            [{"event": "FSDJump", "StarSystem": _SYSTEM_2}],
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION_2}],
            [{"event": "Docked", "StationName": _STATION_2}],
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
            _write_cargo(journal_dir, [])
            with patch("edap.routines.haul_two_way.market_sell") as market_sell_mock:
                market_sell_mock.return_value = RoutineResult(
                    action="market_sell",
                    dispatch=ActionDispatchResult(action="market_sell", status="error", reason="stop after transit"),
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
                    start_phase=Phase.TRANSIT_TO_STATION_2,
                    step_delay_s=0.0,
                    settle_s=0.0,
                    supercruise_exit_settle_s=0.0,
                    boost_settle_s=0.0,
                    dock_timeout_s=30.0,
                    request_timeout_s=10.0,
                    undock_timeout_s=10.0,
                    trade_timeout_s=10.0,
                    open_nav_panel_after_hyperspace_arrival=False,
                    time_fn=_ticking_clock(),
                    sleeper=lambda s: sleep_calls.append(s),
                )

        self.assertEqual(result.dispatch.status, "error")
        self.assertEqual([call["action"] for call in controls.calls].count("FocusLeftPanel"), 1)
        self.assertNotIn(3.0, sleep_calls)

    def test_transit_uses_configured_nav_panel_open_delay(self) -> None:
        controls = FakeShipControls()
        sleep_calls: list[float] = []
        watcher = FakeWatcher([
            [{"event": "FSDJump", "StarSystem": _SYSTEM_2}],
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION_2}],
            [{"event": "Docked", "StationName": _STATION_2}],
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
            _write_cargo(journal_dir, [])
            with patch("edap.routines.haul_two_way.market_sell") as market_sell_mock:
                market_sell_mock.return_value = RoutineResult(
                    action="market_sell",
                    dispatch=ActionDispatchResult(action="market_sell", status="error", reason="stop after transit"),
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
                    start_phase=Phase.TRANSIT_TO_STATION_2,
                    step_delay_s=0.0,
                    settle_s=0.0,
                    supercruise_exit_settle_s=0.0,
                    boost_settle_s=0.0,
                    dock_timeout_s=30.0,
                    request_timeout_s=10.0,
                    undock_timeout_s=10.0,
                    trade_timeout_s=10.0,
                    nav_panel_open_delay_s=1.5,
                    time_fn=_ticking_clock(),
                    sleeper=lambda s: sleep_calls.append(s),
                )

        self.assertEqual(result.dispatch.status, "error")
        self.assertIn(1.5, sleep_calls)
        self.assertNotIn(3.0, sleep_calls)

    def test_resume_in_destination_supercruise_opens_nav_without_waiting_for_new_jump(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([
            [{"event": "SupercruiseExit", "BodyType": "Station"}],
            [],
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": _STATION_2}],
            [{"event": "Docked", "StationName": _STATION_2}],
        ])

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            _write_journal(
                journal_dir,
                {"event": "FSDJump", "StarSystem": _SYSTEM_2},
            )
            _write_cargo(journal_dir, [])
            with patch("edap.routines.haul_two_way.market_sell") as market_sell_mock:
                market_sell_mock.return_value = RoutineResult(
                    action="market_sell",
                    dispatch=ActionDispatchResult(action="market_sell", status="error", reason="stop after transit"),
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
                    start_phase=Phase.TRANSIT_TO_STATION_2,
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

        self.assertEqual(result.dispatch.status, "error")
        self.assertEqual([call["action"] for call in controls.calls].count("FocusLeftPanel"), 2)

    def test_auto_detects_station_2_sell_when_docked_with_station_1_cargo(self) -> None:
        controls = FakeShipControls()
        market_calls: list[tuple[str, str]] = []
        watcher = FakeWatcher([
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
            _write_journal(
                journal_dir,
                {"event": "Location", "Docked": True, "StationName": _STATION_2, "StarSystem": _SYSTEM_2},
            )
            _write_market(
                journal_dir,
                _STATION_2,
                [
                    {"Category": "Metals", "Name": "aluminium", "Name_Localised": _CARGO_1, "DemandBracket": 1, "Stock": 1000},
                    {"Category": "Minerals", "Name": "bertrandite", "Name_Localised": _CARGO_2, "DemandBracket": 1, "Stock": 1000},
                ],
            )
            _write_cargo(journal_dir, [{"Name": "aluminium", "Count": 64, "Stolen": 0}])
            with patch("edap.routines.haul_two_way.market_sell") as market_sell_mock, patch(
                "edap.routines.haul_two_way.market_buy"
            ) as market_buy_mock:
                market_sell_mock.side_effect = lambda controls, watcher, **kwargs: (
                    market_calls.append(("sell", kwargs["target"])) or RoutineResult(
                        action="market_sell",
                        dispatch=ActionDispatchResult(action="market_sell", status="ok"),
                    )
                )

                def fake_buy(controls, watcher, **kwargs):
                    market_calls.append(("buy", kwargs["target"]))
                    _write_cargo(journal_dir, [{"Name": "bertrandite", "Count": 64, "Stolen": 0}])
                    return RoutineResult(
                        action="market_buy",
                        dispatch=ActionDispatchResult(action="market_buy", status="ok"),
                    )

                market_buy_mock.side_effect = fake_buy
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
        self.assertEqual(market_calls[0:2], [("sell", _CARGO_1), ("buy", _CARGO_2)])

    def test_auto_detects_station_2_buy_when_docked_empty(self) -> None:
        controls = FakeShipControls()
        market_calls: list[tuple[str, str]] = []
        watcher = FakeWatcher([
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
            _write_journal(
                journal_dir,
                {"event": "Location", "Docked": True, "StationName": _STATION_2, "StarSystem": _SYSTEM_2},
            )
            _write_market(
                journal_dir,
                _STATION_2,
                [
                    {"Category": "Metals", "Name": "aluminium", "Name_Localised": _CARGO_1, "DemandBracket": 1, "Stock": 1000},
                    {"Category": "Minerals", "Name": "bertrandite", "Name_Localised": _CARGO_2, "DemandBracket": 1, "Stock": 1000},
                ],
            )
            _write_cargo(journal_dir, [])
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
        self.assertEqual(market_calls[0], ("buy", _CARGO_2))

    def test_auto_detects_station_2_drop_and_skips_supercruise_exit_wait(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([])

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            _write_journal(
                journal_dir,
                {"event": "SupercruiseExit", "BodyType": "Station", "StarSystem": _SYSTEM_2},
            )
            _write_cargo(journal_dir, [{"Name": "aluminium", "Count": 64, "Stolen": 0}])

            with patch("edap.routines.haul_two_way.dock") as dock_mock:
                dock_mock.return_value = RoutineResult(
                    action="dock",
                    dispatch=ActionDispatchResult(action="dock", status="error", reason="stop after first dock call"),
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

        self.assertEqual(result.dispatch.status, "error")
        self.assertEqual(dock_mock.call_count, 1)
        self.assertFalse(dock_mock.call_args.kwargs["wait_for_supercruise_exit"])

    def test_auto_detects_station_2_docking_grant_and_waits_for_docked(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([])

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            _write_journal(
                journal_dir,
                {"event": "SupercruiseExit", "BodyType": "Station", "StarSystem": _SYSTEM_2},
                {"event": "DockingGranted", "StationName": _STATION_2, "LandingPad": 7},
            )
            _write_cargo(journal_dir, [{"Name": "aluminium", "Count": 64, "Stolen": 0}])

            with patch("edap.routines.haul_two_way.dock") as dock_mock, patch(
                "edap.routines.haul_two_way.station_refuel_menu"
            ) as station_refuel_menu_mock:
                station_refuel_menu_mock.return_value = RoutineResult(
                    action="UI_Down",
                    dispatch=ActionDispatchResult(action="UI_Down", status="error", reason="stop after wait-for-docked path"),
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

        self.assertEqual(result.dispatch.status, "error")
        dock_mock.assert_not_called()
        station_refuel_menu_mock.assert_called_once()

    def test_auto_detects_station_2_from_market_json_when_journal_lacks_position(self) -> None:
        controls = FakeShipControls()
        market_calls: list[tuple[str, str]] = []
        watcher = FakeWatcher([
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
                _STATION_2,
                [
                    {
                        "Category": "Metals",
                        "Name": "aluminium",
                        "Name_Localised": _CARGO_1,
                        "DemandBracket": 1,
                        "Stock": 1000,
                        "StarSystem": _SYSTEM_2,
                    },
                    {
                        "Category": "Minerals",
                        "Name": "bertrandite",
                        "Name_Localised": _CARGO_2,
                        "DemandBracket": 1,
                        "Stock": 1000,
                        "StarSystem": _SYSTEM_2,
                    },
                ],
            )
            (journal_dir / "Market.json").write_text(
                json.dumps({
                    "StationName": _STATION_2,
                    "StarSystem": _SYSTEM_2,
                    "Items": [],
                }),
                encoding="utf-8",
            )
            _write_cargo(journal_dir, [])
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
        self.assertEqual(market_calls[0], ("buy", _CARGO_2))

    def test_detect_start_phase_prefers_journal_system_over_stale_market_system(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            progress: list[str] = []
            _write_journal(
                journal_dir,
                {"event": "FSDJump", "StarSystem": _SYSTEM_1},
                {"event": "Docked", "StationName": _STATION_1},
            )
            (journal_dir / "Market.json").write_text(
                json.dumps({
                    "StationName": _STATION_1,
                    "StarSystem": _SYSTEM_2,
                    "Items": [],
                }),
                encoding="utf-8",
            )
            _write_cargo(journal_dir, [{"Name": "aluminium", "Count": 64, "Stolen": 0}])
            phase = _detect_start_phase(
                journal_dir,
                station_1=StationLeg(
                    index=1,
                    station=_STATION_1,
                    system=_SYSTEM_1,
                    buy_commodity=_CARGO_1,
                    sell_commodity=_CARGO_2,
                ),
                station_2=StationLeg(
                    index=2,
                    station=_STATION_2,
                    system=_SYSTEM_2,
                    buy_commodity=_CARGO_2,
                    sell_commodity=_CARGO_1,
                ),
                progress_fn=progress.append,
            )

        self.assertEqual(phase, Phase.AT_STATION_1_BUY)
        self.assertTrue(progress)
        self.assertIn(f"system='{_SYSTEM_1}'", progress[-1])
        self.assertNotIn(f"system='{_SYSTEM_2}'", progress[-1])

    def test_undock_aborts_haul_on_no_track_timeout_and_logs_replay_hint(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([
            [],
            [{"event": "Undocked", "StationName": _STATION_1}],
        ])
        announcements: list[tuple[object, dict[str, object]]] = []
        messages: list[str] = []

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
            _write_cargo(journal_dir, [])

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
                start_phase=Phase.UNDOCK_STATION_1,
                step_delay_s=0.0,
                settle_s=0.0,
                boost_settle_s=0.0,
                dock_timeout_s=30.0,
                request_timeout_s=10.0,
                undock_timeout_s=10.0,
                undock_no_track_timeout_s=0.0,
                trade_timeout_s=10.0,
                time_fn=_ticking_clock(),
                sleeper=lambda _: None,
                progress_fn=messages.append,
                announce_fn=lambda message_id, **values: announcements.append((message_id, values)),
            )

        self.assertEqual(result.dispatch.status, "error")
        self.assertTrue(any("replay / ctrl-r" in message for message in messages))
        self.assertIn((AnnouncementId.HAUL_ABORTED, {}), announcements)
        actions = [call["action"] for call in controls.calls]
        self.assertIn("GalaxyMapOpen", actions)
        self.assertNotIn("UseBoostJuice", actions)

    def test_skips_sell_when_cargo_empty(self) -> None:
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
            _write_cargo(journal_dir, [])
            with patch("edap.routines.haul_two_way.market_sell") as market_sell_mock, patch(
                "edap.routines.haul_two_way.market_buy"
            ) as market_buy_mock:
                market_sell_mock.side_effect = lambda controls, watcher, **kwargs: (
                    market_calls.append(("sell", kwargs["target"])) or RoutineResult(
                        action="market_sell",
                        dispatch=ActionDispatchResult(action="market_sell", status="ok"),
                    )
                )
                def fake_buy(controls, watcher, **kwargs):
                    market_calls.append(("buy", kwargs["target"]))
                    _write_cargo(
                        journal_dir,
                        [{"Name": kwargs["target"].lower(), "Count": 64, "Stolen": 0}],
                    )
                    return RoutineResult(
                        action="market_buy",
                        dispatch=ActionDispatchResult(action="market_buy", status="ok"),
                    )

                market_buy_mock.side_effect = fake_buy
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
                ("buy", _CARGO_1),
                ("sell", _CARGO_1),
                ("buy", _CARGO_2),
            ],
        )

    def test_post_sell_settle_sleeps_between_sell_and_buy(self) -> None:
        controls = FakeShipControls()
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
        sleep_calls: list[float] = []

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
            _write_cargo(
                journal_dir,
                [{"Name": "bertrandite", "Count": 64, "Stolen": 0}],
            )
            with patch("edap.routines.haul_two_way.market_sell") as market_sell_mock, patch(
                "edap.routines.haul_two_way.market_buy"
            ) as market_buy_mock:
                market_sell_mock.side_effect = lambda controls, watcher, **kwargs: RoutineResult(
                    action="market_sell",
                    dispatch=ActionDispatchResult(action="market_sell", status="ok"),
                )
                market_buy_mock.side_effect = lambda controls, watcher, **kwargs: RoutineResult(
                    action="market_buy",
                    dispatch=ActionDispatchResult(action="market_buy", status="ok"),
                )
                haul_loop_two_way(
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
                    post_sell_settle_s=2.5,
                    dock_timeout_s=30.0,
                    request_timeout_s=10.0,
                    undock_timeout_s=10.0,
                    trade_timeout_s=10.0,
                    time_fn=_ticking_clock(),
                    sleeper=lambda s: sleep_calls.append(s),
                )

        self.assertEqual(sleep_calls.count(2.5), 2)

    def test_post_sell_settle_skipped_when_cargo_empty(self) -> None:
        controls = FakeShipControls()
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
        sleep_calls: list[float] = []

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
            _write_cargo(journal_dir, [])
            with patch("edap.routines.haul_two_way.market_sell") as market_sell_mock, patch(
                "edap.routines.haul_two_way.market_buy"
            ) as market_buy_mock:
                market_sell_mock.side_effect = lambda controls, watcher, **kwargs: RoutineResult(
                    action="market_sell",
                    dispatch=ActionDispatchResult(action="market_sell", status="ok"),
                )

                def fake_buy(controls, watcher, **kwargs):
                    _write_cargo(
                        journal_dir,
                        [{"Name": kwargs["target"].lower(), "Count": 64, "Stolen": 0}],
                    )
                    return RoutineResult(
                        action="market_buy",
                        dispatch=ActionDispatchResult(action="market_buy", status="ok"),
                    )

                market_buy_mock.side_effect = fake_buy
                haul_loop_two_way(
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
                    post_sell_settle_s=2.5,
                    dock_timeout_s=30.0,
                    request_timeout_s=10.0,
                    undock_timeout_s=10.0,
                    trade_timeout_s=10.0,
                    time_fn=_ticking_clock(),
                    sleeper=lambda s: sleep_calls.append(s),
                )

        # Station 1 sell was skipped (empty cargo), so only the station 2 sell triggers the settle.
        self.assertEqual(sleep_calls.count(2.5), 1)

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
