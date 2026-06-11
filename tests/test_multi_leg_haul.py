from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from edap.actions import ActionDispatchResult
from edap.multi_leg_haul import (
    EXTERNAL_SCHEMA,
    CargoTransfer,
    MultiLegHaulDefinition,
    RouteEndpoint,
    RouteLeg,
    build_route_stops,
    multi_leg_haul_definition_from_data,
    multi_leg_haul_definition_to_external_json,
)
from edap.routines import RoutineResult
from edap.routines.callbacks import noop_announce, noop_progress
from edap.routines.haul_multi_leg import Phase, multi_leg_haul as _multi_leg_haul
from tests.fakes import FakeShipControls, FakeWatcher


def multi_leg_haul(*args, **kwargs):
    kwargs.setdefault("progress_fn", noop_progress)
    kwargs.setdefault("announce_fn", noop_announce)
    return _multi_leg_haul(*args, **kwargs)


def _ticking_clock(step: float = 0.01):
    t = [0.0]

    def fn() -> float:
        value = t[0]
        t[0] += step
        return value

    return fn


def _definition() -> MultiLegHaulDefinition:
    return MultiLegHaulDefinition(
        route_name="Pawelczyk Dock -> Pawelczyk Dock (2 legs)",
        source_provider="spansh",
        source_job="job-123",
        source_url="fixture",
        source_parameters={"max_cargo": "460"},
        legs=(
            RouteLeg(
                index=1,
                source=RouteEndpoint(system="HIP 58412", station="Pawelczyk Dock"),
                destination=RouteEndpoint(system="HIP 68076", station="Bolivar Horizons"),
                cargo=(CargoTransfer(commodity="Water Purifiers", amount=460, buy_price=403, sell_price=2086),),
                jump_distance_ly=39.06,
                total_profit=774180,
                cumulative_profit=774180,
            ),
            RouteLeg(
                index=2,
                source=RouteEndpoint(system="HIP 68076", station="Bolivar Horizons"),
                destination=RouteEndpoint(system="HIP 58412", station="Pawelczyk Dock"),
                cargo=(CargoTransfer(commodity="Aluminium", amount=460, buy_price=2674, sell_price=20320),),
                jump_distance_ly=30.06,
                total_profit=8117160,
                cumulative_profit=8891340,
            ),
        ),
    )


class MultiLegHaulDefinitionTests(unittest.TestCase):
    def test_spansh_payload_normalizes_to_external_schema(self) -> None:
        payload = {
            "job": "job-123",
            "parameters": {"max_cargo": "460"},
            "result": [
                {
                    "commodities": [
                        {
                            "amount": 460,
                            "destination_commodity": {"sell_price": 2086},
                            "name": "Water Purifiers",
                            "profit": 1683,
                            "source_commodity": {"buy_price": 403},
                            "total_profit": 774180,
                        }
                    ],
                    "cumulative_profit": 774180,
                    "destination": {"station": "Bolivar Horizons", "system": "HIP 68076"},
                    "distance": 39.0604999487974,
                    "source": {"station": "Pawelczyk Dock", "system": "HIP 58412"},
                    "total_profit": 774180,
                }
            ],
            "state": "completed",
            "status": "ok",
        }

        definition = multi_leg_haul_definition_from_data(payload, source_label="fixture")
        external = multi_leg_haul_definition_to_external_json(definition)

        self.assertEqual(external["schema"], EXTERNAL_SCHEMA)
        self.assertEqual(external["route_name"], "Pawelczyk Dock -> Bolivar Horizons (1 legs)")
        self.assertEqual(external["legs"][0]["cargo"][0]["commodity"], "Water Purifiers")
        self.assertEqual(external["legs"][0]["cargo"][0]["amount"], 460)

    def test_external_round_trip_preserves_leg_data(self) -> None:
        definition = _definition()
        payload = multi_leg_haul_definition_to_external_json(definition)

        loaded = multi_leg_haul_definition_from_data(payload, source_label="fixture")
        stops = build_route_stops(loaded)

        self.assertEqual(loaded.route_name, definition.route_name)
        self.assertEqual(len(loaded.legs), 2)
        self.assertEqual(stops[1].inbound[0].commodity, "Water Purifiers")
        self.assertEqual(stops[1].outbound[0].commodity, "Aluminium")


class MultiLegHaulRoutineTests(unittest.TestCase):
    def test_route_can_resume_midway_from_destination_station(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([
            [],
            [{"event": "Undocked", "StationName": "Bolivar Horizons"}],
            [{"event": "Music", "MusicTrack": "NoTrack"}],
            [{"event": "SupercruiseExit", "BodyType": "Station", "StarSystem": "HIP 58412"}],
            [],
            [{"event": "DockingGranted", "LandingPad": 1, "StationName": "Pawelczyk Dock"}],
            [{"event": "Docked", "StationName": "Pawelczyk Dock"}],
        ])
        definition = _definition()
        market_calls: list[tuple[str, str, str]] = []

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                '{"event":"Docked","StationName":"Bolivar Horizons","StarSystem":"HIP 68076"}\n',
                encoding="utf-8",
            )
            (journal_dir / "Market.json").write_text(
                '{"StationName":"Bolivar Horizons","StarSystem":"HIP 68076","Items":[]}\n',
                encoding="utf-8",
            )
            (journal_dir / "Cargo.json").write_text(
                '{"Inventory":[{"Name":"water purifiers","Name_Localised":"Water Purifiers","Count":460,"Stolen":0}]}\n',
                encoding="utf-8",
            )
            with patch("edap.routines.haul_multi_leg.market_sell") as market_sell_mock, patch(
                "edap.routines.haul_multi_leg.market_buy"
            ) as market_buy_mock:
                def fake_sell(controls, watcher, **kwargs):
                    market_calls.append(("sell", kwargs["target"], kwargs["amount"]))
                    target = kwargs["target"]
                    if target == "Water Purifiers":
                        (journal_dir / "Cargo.json").write_text('{"Inventory":[]}\n', encoding="utf-8")
                    elif target == "Aluminium":
                        (journal_dir / "Cargo.json").write_text('{"Inventory":[]}\n', encoding="utf-8")
                    return RoutineResult(
                        action="market_sell",
                        dispatch=ActionDispatchResult(action="market_sell", status="ok"),
                    )

                def fake_buy(controls, watcher, **kwargs):
                    market_calls.append(("buy", kwargs["target"], kwargs["amount"]))
                    if kwargs["target"] == "Aluminium":
                        (journal_dir / "Cargo.json").write_text(
                            '{"Inventory":[{"Name":"aluminium","Name_Localised":"Aluminium","Count":460,"Stolen":0}]}\n',
                            encoding="utf-8",
                        )
                    return RoutineResult(
                        action="market_buy",
                        dispatch=ActionDispatchResult(action="market_buy", status="ok"),
                    )

                market_sell_mock.side_effect = fake_sell
                market_buy_mock.side_effect = fake_buy
                result = multi_leg_haul(
                    controls,
                    watcher,
                    definition=definition,
                    journal_dir=journal_dir,
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
                ("sell", "Water Purifiers", "460"),
                ("buy", "Aluminium", "460"),
                ("sell", "Aluminium", "460"),
            ],
        )
        self.assertIn("HyperSuperCombination", [call["action"] for call in controls.calls])

    def test_stop_requested_halts_before_departure(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([])
        definition = _definition()

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                '{"event":"Docked","StationName":"Pawelczyk Dock","StarSystem":"HIP 58412"}\n',
                encoding="utf-8",
            )
            (journal_dir / "Market.json").write_text(
                '{"StationName":"Pawelczyk Dock","StarSystem":"HIP 58412","Items":[]}\n',
                encoding="utf-8",
            )
            (journal_dir / "Cargo.json").write_text(
                '{"Inventory":[]}\n',
                encoding="utf-8",
            )
            with patch("edap.routines.haul_multi_leg.market_buy") as market_buy_mock:
                market_buy_mock.return_value = RoutineResult(
                    action="market_buy",
                    dispatch=ActionDispatchResult(action="market_buy", status="ok"),
                )
                result = multi_leg_haul(
                    controls,
                    watcher,
                    definition=definition,
                    journal_dir=journal_dir,
                    step_delay_s=0.0,
                    settle_s=0.0,
                    dock_timeout_s=30.0,
                    request_timeout_s=10.0,
                    undock_timeout_s=10.0,
                    trade_timeout_s=10.0,
                    stop_requested_fn=lambda: True,
                    time_fn=_ticking_clock(),
                    sleeper=lambda _: None,
                )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual([call["action"] for call in controls.calls], [])


if __name__ == "__main__":
    unittest.main()
