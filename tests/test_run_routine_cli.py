from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import run_routine
from edap.config import load_config
from edap.runtime import LoadedConfig


class _FakeControls:
    def __init__(self, result_payload: dict[str, object]) -> None:
        self.calls: list[dict[str, object]] = []
        self._result_payload = result_payload

    def set_speed_zero(self, repeat: int = 1, hold_s: float = 0.0):
        self.calls.append({"repeat": repeat, "hold_s": hold_s})

        class _Result:
            def __init__(self, payload: dict[str, object]) -> None:
                self.status = str(payload["status"])
                self._payload = payload

            def to_dict(self) -> dict[str, object]:
                return dict(self._payload)

        return _Result(self._result_payload)


class RunRoutineCliTests(unittest.TestCase):
    def test_main_runs_auto_zero_routine_and_emits_json(self) -> None:
        fake_controls = _FakeControls({"action": "SetSpeedZero", "status": "ok"})
        loaded = LoadedConfig(
            config=load_config("config.example.toml"),
            config_path="config.example.toml",
            used_example_config_fallback=True,
        )
        runtime = type(
            "_Runtime",
            (),
            {
                "journal": type(
                    "_Journal",
                    (),
                    {
                        "effective_path": Path("/tmp/Journal"),
                        "cli_source_status": staticmethod(lambda: "auto_detected"),
                    },
                )(),
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
        fake_result = type(
            "_RoutineResult",
            (),
            {
                "action": "SetSpeedZero",
                "dispatch": fake_controls.set_speed_zero(),
                "wait_s": 0.0,
                "trigger_event": {"event": "SupercruiseExit", "StarSystem": "Achenar"},
            },
        )()

        with patch("run_routine.load_config_with_fallback", return_value=loaded), patch(
            "run_routine.build_runtime_context",
            return_value=runtime,
        ), patch(
            "run_routine.ShipControls.from_binding_lookup",
            return_value=fake_controls,
        ), patch(
            "run_routine.JournalWatcher",
            return_value=type("_Watcher", (), {"watch": lambda self: iter(())})(),
        ), patch(
            "run_routine.auto_zero_throttle_on_arrival",
            return_value=fake_result,
        ) as auto_zero_mock, patch("sys.stdout", new_callable=io.StringIO) as stdout, patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            with patch("sys.argv", ["run_routine.py", "--routine", "auto_zero_throttle_on_arrival"]):
                exit_code = run_routine.main()

        self.assertEqual(exit_code, 0)
        auto_zero_mock.assert_called_once()
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["routine"], "auto_zero_throttle_on_arrival")
        self.assertEqual(payload["journal_source"], "auto_detected")
        self.assertEqual(payload["bindings_source"], "auto_detected")
        self.assertEqual(payload["result"]["trigger_event"]["event"], "SupercruiseExit")
        self.assertIn("Watching /tmp/Journal for SupercruiseExit events", stderr.getvalue())

    def test_main_returns_error_when_journal_dir_cannot_be_resolved(self) -> None:
        loaded = LoadedConfig(
            config=load_config("config.example.toml"),
            config_path="config.example.toml",
            used_example_config_fallback=True,
        )
        runtime = type(
            "_Runtime",
            (),
            {
                "journal": type(
                    "_Journal",
                    (),
                    {
                        "effective_path": None,
                        "cli_source_status": staticmethod(lambda: "auto_detect_not_found"),
                    },
                )(),
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

        with patch("run_routine.load_config_with_fallback", return_value=loaded), patch(
            "run_routine.build_runtime_context",
            return_value=runtime,
        ), patch("sys.stdout", new_callable=io.StringIO), patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            with patch("sys.argv", ["run_routine.py", "--routine", "auto_zero_throttle_on_arrival"]):
                exit_code = run_routine.main()

        self.assertEqual(exit_code, 2)
        self.assertIn("Could not resolve journal directory.", stderr.getvalue())

    def test_main_returns_130_on_keyboard_interrupt(self) -> None:
        fake_controls = _FakeControls({"action": "SetSpeedZero", "status": "ok"})
        loaded = LoadedConfig(
            config=load_config("config.example.toml"),
            config_path="config.example.toml",
            used_example_config_fallback=True,
        )
        runtime = type(
            "_Runtime",
            (),
            {
                "journal": type(
                    "_Journal",
                    (),
                    {
                        "effective_path": Path("/tmp/Journal"),
                        "cli_source_status": staticmethod(lambda: "auto_detected"),
                    },
                )(),
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

        with patch("run_routine.load_config_with_fallback", return_value=loaded), patch(
            "run_routine.build_runtime_context",
            return_value=runtime,
        ), patch(
            "run_routine.ShipControls.from_binding_lookup",
            return_value=fake_controls,
        ), patch(
            "run_routine.auto_zero_throttle_on_arrival",
            side_effect=KeyboardInterrupt,
        ), patch("sys.stdout", new_callable=io.StringIO), patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            with patch("sys.argv", ["run_routine.py", "--routine", "auto_zero_throttle_on_arrival"]):
                exit_code = run_routine.main()

        self.assertEqual(exit_code, 130)
        self.assertIn("Interrupted.", stderr.getvalue())
