from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import ship_controls
from edap.config import load_config
from edap.runtime import LoadedConfig


class _FakeControls:
    def __init__(self, expected_result: dict[str, object]) -> None:
        self.expected_result = expected_result
        self.calls: list[dict[str, object]] = []
        self.plans: list[dict[str, object]] = []

    def plan_action(self, action: str, *, repeat: int = 1, hold_s: float | None = None, total_s: float | None = None):
        self.plans.append({"action": action, "repeat": repeat, "hold_s": hold_s, "total_s": total_s})
        return type(
            "_Plan",
            (),
            {"action": action, "repeat": 3 if total_s else repeat, "hold_s": 0.2 if hold_s is None else hold_s, "total_s": total_s},
        )()

    def dispatch_action(
        self,
        action: str,
        *,
        repeat: int = 1,
        hold_s: float | None = None,
        total_s: float | None = None,
    ):
        self.calls.append({"action": action, "repeat": repeat, "hold_s": hold_s, "total_s": total_s})

        class _Result:
            def __init__(self, payload: dict[str, object]) -> None:
                self.status = payload["status"]
                self._payload = payload

            def to_dict(self) -> dict[str, object]:
                return dict(self._payload)

        return _Result(self.expected_result)


class ShipControlsCliTests(unittest.TestCase):
    def test_parse_sequence_supports_per_step_fields(self) -> None:
        steps = ship_controls._parse_sequence("SetSpeedZero; RollLeftButton total=0.45; UI_Select repeat=2 hold=0.1 delay=5")

        self.assertEqual(
            steps,
            [
                ship_controls.SequenceStep(action="SetSpeedZero", repeat=None, hold_s=None, total_s=None),
                ship_controls.SequenceStep(action="RollLeftButton", repeat=None, hold_s=None, total_s=0.45),
                ship_controls.SequenceStep(action="UI_Select", repeat=2, hold_s=0.1, total_s=None, delay_s=5.0),
            ],
        )

    def test_main_dispatches_action_and_emits_json(self) -> None:
        fake_controls = _FakeControls({"action": "RollLeftButton", "status": "ok"})
        loaded = LoadedConfig(
            config=load_config("config.example.toml"),
            config_path="config.example.toml",
            used_example_config_fallback=True,
        )
        runtime = type(
            "_Runtime",
            (),
            {
                "bindings": type(
                    "_Bindings",
                    (),
                    {
                        "effective_path": Path("/tmp/Custom.binds"),
                        "cli_source_status": staticmethod(lambda: "auto_detected"),
                    },
                )(),
                "input_controller": object(),
                "binding_lookup": object(),
            },
        )()

        with patch("ship_controls.load_config_with_fallback", return_value=loaded), patch(
            "ship_controls.build_runtime_context",
            return_value=runtime,
        ), patch("ship_controls.ShipControls.from_binding_lookup",
            return_value=fake_controls,
        ), patch("sys.stdout", new_callable=io.StringIO) as stdout, patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            with patch("sys.argv", ["ship_controls.py", "--action", "RollLeftButton", "--repeat", "2", "--hold-seconds", "0.1"]):
                exit_code = ship_controls.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            fake_controls.calls,
            [{"action": "RollLeftButton", "repeat": 2, "hold_s": 0.1, "total_s": None}],
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["bindings_source"], "auto_detected")
        self.assertEqual(payload["result"]["status"], "ok")
        self.assertFalse(payload["sequence"])
        self.assertIn("Sending RollLeftButton 2 times", stderr.getvalue())

    def test_main_uses_total_seconds_plan_for_continuous_action(self) -> None:
        fake_controls = _FakeControls({"action": "RollLeftButton", "status": "ok"})
        loaded = LoadedConfig(
            config=load_config("config.example.toml"),
            config_path="config.example.toml",
            used_example_config_fallback=True,
        )
        runtime = type(
            "_Runtime",
            (),
            {
                "bindings": type(
                    "_Bindings",
                    (),
                    {
                        "effective_path": Path("/tmp/Custom.binds"),
                        "cli_source_status": staticmethod(lambda: "auto_detected"),
                    },
                )(),
                "input_controller": object(),
                "binding_lookup": object(),
            },
        )()

        with patch("ship_controls.load_config_with_fallback", return_value=loaded), patch(
            "ship_controls.build_runtime_context",
            return_value=runtime,
        ), patch("ship_controls.ShipControls.from_binding_lookup",
            return_value=fake_controls,
        ), patch("sys.stdout", new_callable=io.StringIO) as stdout, patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            with patch("sys.argv", ["ship_controls.py", "--action", "RollLeftButton", "--total-seconds", "0.45"]):
                exit_code = ship_controls.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            fake_controls.calls,
            [{"action": "RollLeftButton", "repeat": 1, "hold_s": None, "total_s": 0.45}],
        )
        self.assertIn("Planned RollLeftButton for total 0.45s as 3 activations at 0.20s each.", stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["result"]["status"], "ok")

    def test_main_dispatches_sequence_and_emits_results_array(self) -> None:
        fake_controls = _FakeControls({"status": "ok"})
        loaded = LoadedConfig(
            config=load_config("config.example.toml"),
            config_path="config.example.toml",
            used_example_config_fallback=True,
        )
        runtime = type(
            "_Runtime",
            (),
            {
                "bindings": type(
                    "_Bindings",
                    (),
                    {
                        "effective_path": Path("/tmp/Custom.binds"),
                        "cli_source_status": staticmethod(lambda: "auto_detected"),
                    },
                )(),
                "input_controller": object(),
                "binding_lookup": object(),
            },
        )()

        with patch("ship_controls.load_config_with_fallback", return_value=loaded), patch(
            "ship_controls.build_runtime_context",
            return_value=runtime,
        ), patch("ship_controls.ShipControls.from_binding_lookup",
            return_value=fake_controls,
        ), patch("ship_controls.sleep") as sleep_mock, patch(
            "ship_controls._sleep_with_countdown",
            wraps=ship_controls._sleep_with_countdown,
        ), patch("sys.stdout", new_callable=io.StringIO) as stdout, patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            with patch(
                "sys.argv",
                [
                    "ship_controls.py",
                    "--sequence",
                    "SetSpeedZero; RollLeftButton total=0.45; UI_Select repeat=2 hold=0.1 delay=5",
                ],
            ):
                exit_code = ship_controls.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            fake_controls.calls,
            [
                {"action": "SetSpeedZero", "repeat": 1, "hold_s": None, "total_s": None},
                {"action": "RollLeftButton", "repeat": 1, "hold_s": None, "total_s": 0.45},
                {"action": "UI_Select", "repeat": 2, "hold_s": 0.1, "total_s": None},
            ],
        )
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["sequence"])
        self.assertEqual(len(payload["results"]), 3)
        self.assertEqual(payload["results"][2]["delay_s"], 5.0)
        self.assertIn("Step 1/3", stderr.getvalue())
        self.assertIn("Step 2/3", stderr.getvalue())
        self.assertIn("Step 3/3", stderr.getvalue())
        self.assertIn("Sending UI_Select in 5s", stderr.getvalue())
        self.assertEqual(sleep_mock.call_count, 5)

    def test_main_dispatches_station_refuel_preset(self) -> None:
        fake_controls = _FakeControls({"status": "ok"})
        loaded = LoadedConfig(
            config=load_config("config.example.toml"),
            config_path="config.example.toml",
            used_example_config_fallback=True,
        )
        runtime = type(
            "_Runtime",
            (),
            {
                "bindings": type(
                    "_Bindings",
                    (),
                    {
                        "effective_path": Path("/tmp/Custom.binds"),
                        "cli_source_status": staticmethod(lambda: "auto_detected"),
                    },
                )(),
                "input_controller": object(),
                "binding_lookup": object(),
            },
        )()

        with patch("ship_controls.load_config_with_fallback", return_value=loaded), patch(
            "ship_controls.build_runtime_context",
            return_value=runtime,
        ), patch(
            "ship_controls.ShipControls.from_binding_lookup",
            return_value=fake_controls,
        ), patch("ship_controls.sleep") as sleep_mock, patch(
            "sys.stdout", new_callable=io.StringIO
        ) as stdout, patch("sys.stderr", new_callable=io.StringIO) as stderr:
            with patch(
                "sys.argv",
                [
                    "ship_controls.py",
                    "--preset",
                    "station_refuel_menu",
                ],
            ):
                exit_code = ship_controls.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            fake_controls.calls,
            [
                {"action": "UI_Up", "repeat": 1, "hold_s": None, "total_s": None},
                {"action": "UI_Select", "repeat": 1, "hold_s": None, "total_s": None},
                {"action": "UI_Down", "repeat": 1, "hold_s": None, "total_s": None},
            ],
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["preset"], "station_refuel_menu")
        self.assertEqual(len(payload["results"]), 3)
        self.assertIn("Sending UI_Select in 1s", stderr.getvalue())
        self.assertIn("Sending UI_Down in 1s", stderr.getvalue())
        self.assertEqual(sleep_mock.call_count, 2)

    def test_countdown_logs_to_stderr(self) -> None:
        with patch("ship_controls.sleep") as sleep_mock, patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            ship_controls._sleep_with_countdown("RollLeftButton", 2.0)

        self.assertEqual(sleep_mock.call_count, 2)
        self.assertIn("Sending RollLeftButton in 2s", stderr.getvalue())
        self.assertIn("Sending RollLeftButton in 1s", stderr.getvalue())
