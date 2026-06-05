from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import run_routine
from edap.binding_lookup import build_binding_lookup
from edap.bindings import Binding
from edap.config import load_config
from edap.runtime import LoadedConfig


class _FakeControls:
    def __init__(self, result_payload: dict[str, object]) -> None:
        self.calls: list[dict[str, object]] = []
        self._result_payload = result_payload

    def set_speed_zero(self, repeat: int = 1, hold_s: float = 0.0):
        self.calls.append({"action": "SetSpeedZero", "repeat": repeat, "hold_s": hold_s})

        class _Result:
            def __init__(self, payload: dict[str, object]) -> None:
                self.status = str(payload["status"])
                self._payload = payload

            def to_dict(self) -> dict[str, object]:
                return dict(self._payload)

        return _Result(self._result_payload)

    def hyper_super_combination(self, repeat: int = 1, hold_s: float = 0.0):
        self.calls.append({"action": "HyperSuperCombination", "repeat": repeat, "hold_s": hold_s})

        class _Result:
            def __init__(self, payload: dict[str, object]) -> None:
                self.status = str(payload["status"])
                self._payload = payload

            def to_dict(self) -> dict[str, object]:
                return dict(self._payload)

        return _Result(self._result_payload)

    def focus_left_panel(self, repeat: int = 1, hold_s: float = 0.0):
        self.calls.append({"action": "FocusLeftPanel", "repeat": repeat, "hold_s": hold_s})
        return self.set_speed_zero(repeat=repeat, hold_s=hold_s)

    def ui_back(self, repeat: int = 1, hold_s: float = 0.0):
        self.calls.append({"action": "UI_Back", "repeat": repeat, "hold_s": hold_s})
        return self.set_speed_zero(repeat=repeat, hold_s=hold_s)

    def cycle_next_panel(self, repeat: int = 1, hold_s: float = 0.0):
        self.calls.append({"action": "CycleNextPanel", "repeat": repeat, "hold_s": hold_s})
        return self.set_speed_zero(repeat=repeat, hold_s=hold_s)

    def cycle_previous_panel(self, repeat: int = 1, hold_s: float = 0.0):
        self.calls.append({"action": "CyclePreviousPanel", "repeat": repeat, "hold_s": hold_s})
        return self.set_speed_zero(repeat=repeat, hold_s=hold_s)

    def ui_up(self, repeat: int = 1, hold_s: float = 0.0):
        self.calls.append({"action": "UI_Up", "repeat": repeat, "hold_s": hold_s})
        return self.set_speed_zero(repeat=repeat, hold_s=hold_s)

    def ui_right(self, repeat: int = 1, hold_s: float = 0.0):
        self.calls.append({"action": "UI_Right", "repeat": repeat, "hold_s": hold_s})
        return self.set_speed_zero(repeat=repeat, hold_s=hold_s)

    def ui_select(self, repeat: int = 1, hold_s: float = 0.0):
        self.calls.append({"action": "UI_Select", "repeat": repeat, "hold_s": hold_s})
        return self.set_speed_zero(repeat=repeat, hold_s=hold_s)

    def ui_down(self, repeat: int = 1, hold_s: float = 0.0):
        self.calls.append({"action": "UI_Down", "repeat": repeat, "hold_s": hold_s})
        return self.set_speed_zero(repeat=repeat, hold_s=hold_s)


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
                "binding_lookup": build_binding_lookup(
                    bindings={"SetSpeedZero": Binding(key="X")},
                    actions=["SetSpeedZero"],
                ),
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
                "details": None,
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
        self.assertIn("  SetSpeedZero -> x", stderr.getvalue())
        self.assertIsNone(payload["event_log_path"])

    def test_main_runs_jump_routine_and_emits_json(self) -> None:
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
                "binding_lookup": build_binding_lookup(
                    bindings={
                        "SetSpeedZero": Binding(key="X"),
                        "HyperSuperCombination": Binding(key="J", modifier="LeftShift"),
                    },
                    actions=["SetSpeedZero", "HyperSuperCombination"],
                ),
            },
        )()
        fake_result = type(
            "_RoutineResult",
            (),
            {
                "action": "HyperSuperCombination",
                "dispatch": fake_controls.set_speed_zero(),
                "wait_s": 0.0,
                "trigger_event": {"event": "FSDJump", "StarSystem": "Achenar"},
                "details": {"attempt": 1, "followup_action": "SetSpeedZero"},
            },
        )()

        with patch("run_routine.load_config_with_fallback", return_value=loaded), patch(
            "run_routine.build_runtime_context",
            return_value=runtime,
        ) as build_runtime_context_mock, patch(
            "run_routine.ShipControls.from_binding_lookup",
            return_value=fake_controls,
        ), patch(
            "run_routine.JournalWatcher",
            return_value=type("_Watcher", (), {"watch": lambda self: iter(()), "poll": lambda self: []})(),
        ), patch(
            "run_routine.jump",
            return_value=fake_result,
        ) as jump_mock, patch("sys.stdout", new_callable=io.StringIO) as stdout, patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            with patch("sys.argv", ["run_routine.py", "--routine", "jump"]):
                exit_code = run_routine.main()

        self.assertEqual(exit_code, 0)
        build_runtime_context_mock.assert_called_once_with(loaded.config, actions=["SetSpeedZero", "HyperSuperCombination"])
        jump_mock.assert_called_once()
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["routine"], "jump")
        self.assertEqual(payload["result"]["trigger_event"]["event"], "FSDJump")
        self.assertEqual(payload["result"]["details"]["followup_action"], "SetSpeedZero")
        self.assertIn("  HyperSuperCombination -> left_shift+j", stderr.getvalue())
        self.assertIn("  SetSpeedZero -> x", stderr.getvalue())
        self.assertIsNone(payload["event_log_path"])

    def test_main_runs_station_refuel_menu_routine_and_emits_json(self) -> None:
        fake_controls = _FakeControls({"action": "UI_Down", "status": "ok"})
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
                "binding_lookup": build_binding_lookup(
                    bindings={
                        "UI_Up": Binding(key="UpArrow"),
                        "UI_Select": Binding(key="Space"),
                        "UI_Down": Binding(key="DownArrow"),
                    },
                    actions=["UI_Up", "UI_Select", "UI_Down"],
                ),
            },
        )()
        fake_result = type(
            "_RoutineResult",
            (),
            {
                "action": "UI_Down",
                "dispatch": fake_controls.set_speed_zero(),
                "wait_s": 1.0,
                "trigger_event": None,
                "details": {"phase": "ui_down"},
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
            return_value=type("_Watcher", (), {"watch": lambda self: iter(()), "poll": lambda self: []})(),
        ), patch(
            "run_routine.station_refuel_menu",
            return_value=fake_result,
        ) as station_refuel_menu_mock, patch("sys.stdout", new_callable=io.StringIO) as stdout, patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            with patch("sys.argv", ["run_routine.py", "--routine", "station_refuel_menu"]):
                exit_code = run_routine.main()

        self.assertEqual(exit_code, 0)
        station_refuel_menu_mock.assert_called_once()
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["routine"], "station_refuel_menu")
        self.assertEqual(payload["journal_dir"], "/tmp/Journal")
        self.assertIn("  UI_Up -> up", stderr.getvalue())
        self.assertIn("  UI_Select -> space", stderr.getvalue())
        self.assertIn("  UI_Down -> down", stderr.getvalue())
        self.assertIn("Watching /tmp/Journal for Docked events", stderr.getvalue())

    def test_main_runs_dock_routine_and_emits_json(self) -> None:
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
                "binding_lookup": build_binding_lookup(
                    bindings={
                        "SetSpeedZero": Binding(key="X"),
                        "FocusLeftPanel": Binding(key="1"),
                        "UI_Back": Binding(key="Backspace"),
                        "CycleNextPanel": Binding(key="E"),
                        "CyclePreviousPanel": Binding(key="Q"),
                        "UI_Up": Binding(key="UpArrow"),
                        "UI_Right": Binding(key="RightArrow"),
                        "UI_Select": Binding(key="Space"),
                        "UI_Down": Binding(key="DownArrow"),
                    },
                    actions=[
                        "SetSpeedZero",
                        "FocusLeftPanel",
                        "UI_Back",
                        "CycleNextPanel",
                        "CyclePreviousPanel",
                        "UI_Up",
                        "UI_Right",
                        "UI_Select",
                        "UI_Down",
                    ],
                ),
            },
        )()
        fake_result = type(
            "_RoutineResult",
            (),
            {
                "action": "UI_Down",
                "dispatch": fake_controls.set_speed_zero(),
                "wait_s": 3.0,
                "trigger_event": {"event": "Docked"},
                "details": {"auto_refuel": True, "followup_action": "station_refuel_menu"},
            },
        )()

        with patch("run_routine.load_config_with_fallback", return_value=loaded), patch(
            "run_routine.build_runtime_context",
            return_value=runtime,
        ) as build_runtime_context_mock, patch(
            "run_routine.ShipControls.from_binding_lookup",
            return_value=fake_controls,
        ), patch(
            "run_routine.JournalWatcher",
            return_value=type("_Watcher", (), {"watch": lambda self: iter(()), "poll": lambda self: []})(),
        ), patch(
            "run_routine.dock",
            return_value=fake_result,
        ) as dock_mock, patch("sys.stdout", new_callable=io.StringIO) as stdout, patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            with patch(
                "sys.argv",
                ["run_routine.py", "--routine", "dock", "--skip-supercruise-exit", "--auto-refuel"],
            ):
                exit_code = run_routine.main()

        self.assertEqual(exit_code, 0)
        build_runtime_context_mock.assert_called_once_with(
            loaded.config,
            actions=[
                "SetSpeedZero",
                "FocusLeftPanel",
                "UI_Back",
                "CycleNextPanel",
                "CyclePreviousPanel",
                "UI_Up",
                "UI_Right",
                "UI_Select",
                "UI_Down",
            ],
        )
        dock_mock.assert_called_once()
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["routine"], "dock")
        self.assertEqual(payload["skip_supercruise_exit"], True)
        self.assertEqual(payload["auto_refuel"], True)
        self.assertEqual(payload["result"]["details"]["followup_action"], "station_refuel_menu")
        self.assertIn("Watching /tmp/Journal for approach and docking events", stderr.getvalue())
        self.assertIn("  FocusLeftPanel -> 1", stderr.getvalue())
        self.assertIn("  CyclePreviousPanel -> q", stderr.getvalue())
        self.assertIn("  UI_Down -> down", stderr.getvalue())

    def test_main_can_log_events_to_file(self) -> None:
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
                "binding_lookup": build_binding_lookup(
                    bindings={"SetSpeedZero": Binding(key="X")},
                    actions=["SetSpeedZero"],
                ),
            },
        )()
        fake_result = type(
            "_RoutineResult",
            (),
            {
                "action": "SetSpeedZero",
                "dispatch": fake_controls.set_speed_zero(),
                "wait_s": 0.0,
                "trigger_event": {"event": "SupercruiseExit"},
                "details": None,
            },
        )()

        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.log"
            watcher = run_routine.LoggingJournalWatcher(
                type(
                    "_Watcher",
                    (),
                    {"watch": lambda self: iter(()), "poll": lambda self: []},
                )(),
                log_path,
            )
            with patch("run_routine.load_config_with_fallback", return_value=loaded), patch(
                "run_routine.build_runtime_context",
                return_value=runtime,
            ), patch(
                "run_routine.ShipControls.from_binding_lookup",
                return_value=fake_controls,
            ), patch(
                "run_routine.JournalWatcher",
                return_value=type("_InnerWatcher", (), {"watch": lambda self: iter(()), "poll": lambda self: []})(),
            ), patch(
                "run_routine.LoggingJournalWatcher",
                return_value=watcher,
            ), patch(
                "run_routine.auto_zero_throttle_on_arrival",
                return_value=fake_result,
            ), patch("sys.stdout", new_callable=io.StringIO) as stdout, patch(
                "sys.stderr", new_callable=io.StringIO
            ) as stderr:
                with patch(
                    "sys.argv",
                    [
                        "run_routine.py",
                        "--routine",
                        "auto_zero_throttle_on_arrival",
                        "--log-events",
                        "--event-log-path",
                        str(log_path),
                    ],
                ):
                    exit_code = run_routine.main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["event_log_path"], str(log_path))
        self.assertIn(f"Logging raw journal events to {log_path}", stderr.getvalue())

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
                "binding_lookup": build_binding_lookup(
                    bindings={"SetSpeedZero": Binding(key="X")},
                    actions=["SetSpeedZero"],
                ),
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
                "binding_lookup": build_binding_lookup(
                    bindings={"SetSpeedZero": Binding(key="X")},
                    actions=["SetSpeedZero"],
                ),
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
