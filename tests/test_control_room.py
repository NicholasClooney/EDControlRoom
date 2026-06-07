from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from control_room import (
    ControlRoomApp,
    _ALL_ROUTINE_ACTIONS,
    _build_log_text,
    _cargo_summary_lines,
)
from edap.actions import ActionDispatchResult
from edap.config import (
    AppConfig,
    CaptureConfig,
    CaptureRegionConfig,
    ControlRoomConfig,
    ControlsConfig,
    PathsConfig,
    RuntimeConfig,
    ScreenConfig,
)
from edap.control_room.events import apply_ship_event
from edap.control_room.models import ShipState
from edap.control_room_state import CommandHistoryEntry
from edap.routines import RoutineResult
from edap.runtime import ResolvedPath, RuntimeContext


def _make_config(journal_dir: Path) -> AppConfig:
    return AppConfig(
        paths=PathsConfig(journal_dir=journal_dir, bindings_file=None),
        controls=ControlsConfig(
            start_hotkey="home",
            stop_hotkey="end",
            scanner_mode="off",
            minimum_action_hold_seconds=0.1,
            continuous_action_hold_seconds=0.2,
            step_delay_seconds=0.3,
            galaxy_map_settle_seconds=2.0,
            haul_dock_timeout_seconds=600.0,
            undock_timeout_seconds=30.0,
            mass_lock_escape_safety_delay_seconds=15.0,
            mass_lock_boost_delay_seconds=5.0,
            market_nav_delay_seconds=0.1,
            market_trade_max_attempts=3,
        ),
        screen=ScreenConfig(
            resolution_width=1920,
            resolution_height=1080,
            scale=1.0,
            capture_debug_path=None,
            capture=CaptureConfig(
                mode="fullscreen",
                base_region=CaptureRegionConfig(0.0, 0.0, 1.0, 1.0),
                regions={},
            ),
        ),
        runtime=RuntimeConfig(platform="macos", debug=False),
        control_room=ControlRoomConfig(
            state_file=journal_dir / ".control_room_state.json",
            history_limit=20,
        ),
    )


def _make_context(journal_dir: Path) -> RuntimeContext:
    resolved = ResolvedPath(
        configured={"path": str(journal_dir), "status": "ok", "reason": "test journal dir"},
        auto_detected={"path": str(journal_dir), "status": "ok", "reason": "test journal dir"},
        effective={"path": str(journal_dir), "status": "ok", "source": "configured", "reason": "test journal dir"},
    )
    return RuntimeContext(
        config=_make_config(journal_dir),
        game_paths=None,
        journal=resolved,
        bindings=resolved,
        input_controller=None,
        screen_capture=None,
        binding_lookup=None,
    )


class _FakeWorker:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class _HarnessApp(ControlRoomApp):
    def __init__(self, ctx: RuntimeContext) -> None:
        super().__init__(ctx)
        self.logged: list[str] = []
        self.exit_calls = 0

    def _log(self, msg: str) -> None:
        self.logged.append(msg)

    def exit(self, result=None, return_code: int = 0, message=None) -> None:
        self.exit_calls += 1

    def _finalize_shutdown(self) -> None:
        if self._shutdown_finalized:
            return
        self._shutdown_finalized = True
        self.exit()

    def _refresh_market(self) -> None:  # type: ignore[override]
        return None

    def _refresh_haul_stats(self) -> None:  # type: ignore[override]
        return None

    def _show_resume_picker(self) -> None:  # type: ignore[override]
        if not self._saved_state.history:
            self._log("[dim]No saved command history yet.[/]")
            return
        self._resume_open = True
        self._resume_entries = self._filtered_resume_entries()


class _InputStub:
    def __init__(self) -> None:
        self.placeholder = ""


class ControlRoomCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.app = _HarnessApp(_make_context(Path(self.tmpdir.name)))

    def test_commands_lists_supported_commands(self) -> None:
        self.app._dispatch_command("commands")

        output = "\n".join(self.app.logged)
        self.assertIn("Command: commands", output)
        self.assertIn("Supported commands:", output)
        self.assertIn("dock", output)
        self.assertIn("help", output)
        self.assertIn("q | quit | exit", output)

    def test_help_for_alias_resolves_to_canonical_command(self) -> None:
        self.app._dispatch_command("help set_dest")

        output = "\n".join(self.app.logged)
        self.assertIn("dest", output)
        self.assertIn("dest <system>", output)
        self.assertIn("NavRoute.json", output)

    def test_help_unknown_topic_reports_error(self) -> None:
        self.app._dispatch_command("help mystery")

        output = "\n".join(self.app.logged)
        self.assertIn("Command: help mystery", output)
        self.assertIn("Unknown help topic: mystery", output)

    def test_quit_command_exits_immediately_without_active_routine(self) -> None:
        self.app._dispatch_command("quit")

        self.assertTrue(self.app._shutdown_requested)
        self.assertEqual(self.app.exit_calls, 1)

    def test_request_quit_cancels_active_routine_without_exiting(self) -> None:
        worker = _FakeWorker()
        self.app._routine_active = True
        self.app._routine_worker = worker

        self.app.action_request_quit()

        self.assertFalse(self.app._shutdown_requested)
        self.assertTrue(worker.cancelled)
        self.assertEqual(self.app.exit_calls, 0)

    def test_bootstrap_ship_state_reads_balance_and_cargo_from_status_json(self) -> None:
        journal_dir = Path(self.tmpdir.name)
        (journal_dir / "Journal.240101000000.01.log").write_text(
            json.dumps({
                "event": "Location",
                "Docked": True,
                "StarSystem": "HIP 58412",
                "StationName": "Pawelczyk Dock",
                "FuelLevel": 16.0,
                "FuelCapacity": 32.0,
            }) + "\n",
            encoding="utf-8",
        )
        (journal_dir / "Status.json").write_text(
            json.dumps({
                "Flags": 1,
                "Fuel": {"FuelMain": 16.0, "FuelReservoir": 0.5},
                "Cargo": 24,
                "Balance": 123456789,
            }),
            encoding="utf-8",
        )
        (journal_dir / "Cargo.json").write_text(
            json.dumps({
                "Inventory": [
                    {"Name": "gold", "Name_Localised": "Gold", "Count": 5},
                    {"Name": "silver", "Name_Localised": "Silver", "Count": 7},
                ]
            }),
            encoding="utf-8",
        )

        self.app._bootstrap_ship_state()

        self.assertEqual(self.app._ship.system, "HIP 58412")
        self.assertEqual(self.app._ship.credits, 123456789)
        self.assertEqual(self.app._ship.cargo_count, 24)
        self.assertEqual(len(self.app._ship.cargo_inventory), 2)


class ControlRoomBindingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.app = _HarnessApp(_make_context(Path(self.tmpdir.name)))

    def test_preloaded_actions_cover_mass_lock_escape(self) -> None:
        self.assertIn("SetSpeed100", _ALL_ROUTINE_ACTIONS)
        self.assertIn("UseBoostJuice", _ALL_ROUTINE_ACTIONS)

    def test_undock_command_uses_configured_timeouts(self) -> None:
        captured: dict[str, object] = {}

        self.app._controls = object()
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_sleeper = lambda: (lambda _: None)
        self.app._make_watcher = lambda: object()
        self.app._run_in_thread = lambda fn: fn()

        def fake_undock(controls, watcher, **kwargs):
            captured["controls"] = controls
            captured["watcher"] = watcher
            captured["kwargs"] = kwargs
            return None

        with patch("edap.control_room.routines_station.undock", new=fake_undock):
            self.app._cmd_undock()

        self.assertEqual(captured["kwargs"]["undock_timeout_s"], 30.0)
        self.assertEqual(captured["kwargs"]["step_delay_s"], 0.3)

    def test_escape_command_calls_mass_lock_routine(self) -> None:
        captured: dict[str, object] = {}

        self.app._controls = object()
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_sleeper = lambda: (lambda _: None)
        self.app._run_in_thread = lambda fn: fn()

        def fake_escape_mass_lock(controls, **kwargs):
            captured["controls"] = controls
            captured["kwargs"] = kwargs
            return None

        with patch("edap.control_room.routines_movement.escape_mass_lock", new=fake_escape_mass_lock):
            self.app._cmd_escape()

        self.assertEqual(captured["kwargs"]["boost_delay_s"], 5.0)
        self.assertEqual(captured["kwargs"]["step_delay_s"], 0.3)

    def test_boost_command_dispatches_three_boosts(self) -> None:
        controls = object()
        dispatch = ActionDispatchResult(action="UseBoostJuice", status="ok")
        captured: dict[str, object] = {}

        class _BoostControls:
            def boost(self, repeat: int = 1, hold_s: float | None = None) -> ActionDispatchResult:
                captured["repeat"] = repeat
                captured["hold_s"] = hold_s
                return dispatch

        self.app._controls = controls
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: _BoostControls()
        self.app._run_in_thread = lambda fn: fn()

        result = self.app._cmd_boost()

        self.assertIsNone(result)
        self.assertEqual(captured["repeat"], 3)
        self.assertIsNone(captured["hold_s"])
        self.assertIn("Boosting 3x...", self.app.logged)

    def test_boost_command_history_is_distinct_from_escape(self) -> None:
        called: list[str] = []
        self.app._cmd_boost = lambda: called.append("boost")
        self.app._cmd_escape = lambda: called.append("escape")

        self.app._dispatch_command("boost")
        self.app._dispatch_command("escape")

        self.assertEqual(called, ["boost", "escape"])
        self.assertEqual(self.app._saved_state.history[-2].command, "boost")
        self.assertEqual(self.app._saved_state.history[-1].command, "escape")

    def test_sell_all_falls_back_to_cargo_json_when_live_manifest_is_empty(self) -> None:
        cargo_path = Path(self.tmpdir.name) / "Cargo.json"
        cargo_path.write_text(json.dumps({
            "Inventory": [
                {"Name": "aluminium", "Name_Localised": "Aluminium", "Count": 12, "Stolen": 0},
            ]
        }))

        captured_targets: list[str] = []
        self.app._controls = object()
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_sleeper = lambda: (lambda _: None)
        self.app._make_watcher = lambda: object()
        self.app._run_in_thread = lambda fn: fn()
        self.app._raise_if_worker_cancelled = lambda: None
        self.app.call_from_thread = lambda fn, *args, **kwargs: fn(*args, **kwargs)

        def fake_market_sell(controls, watcher, **kwargs):
            captured_targets.append(kwargs["target"])
            return RoutineResult(
                action="market_sell",
                dispatch=ActionDispatchResult(action="market_sell", status="ok"),
            )

        with patch("edap.control_room.routines_trade.market_sell", new=fake_market_sell):
            self.app._sell_all()

        output = "\n".join(self.app.logged)
        self.assertEqual(captured_targets, ["Aluminium"])
        self.assertIn("Cargo.json fallback", output)
        self.assertIn("Sell-all complete", output)
        self.assertNotIn("Nothing sellable in cargo", output)

    def test_haul_dispatch_does_not_require_starting_at_sell_station(self) -> None:
        captured: dict[str, object] = {}

        self.app._ship.status = "in_supercruise"
        self.app._ship.station = ""
        self.app._ship.system = "Sol"
        self.app._haul_params = {
            "commodity": "Aluminium",
            "buy_station": "Trevithick Dock",
            "sell_station": "Pawelczyk Dock",
            "sell_system": "Sol",
            "buy_system": "Achenar",
            "galaxy_map_settle": "",
            "dock_timeout": "",
        }
        self.app._controls = object()
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_sleeper = lambda: (lambda _: None)
        self.app._make_watcher = lambda: object()
        self.app._run_in_thread = lambda fn: fn()

        def fake_haul_loop(controls, watcher, **kwargs):
            captured["controls"] = controls
            captured["watcher"] = watcher
            captured["kwargs"] = kwargs
            return RoutineResult(
                action="haul_loop",
                dispatch=ActionDispatchResult(action="haul_loop", status="ok"),
            )

        with patch("edap.control_room.routines_haul.haul_loop", new=fake_haul_loop):
            self.app._dispatch_haul_loop()

        self.assertIn("kwargs", captured)
        self.assertFalse(any("requires you to be docked at the sell station" in msg for msg in self.app.logged))
        self.assertIn("Starting haul loop:", "\n".join(self.app.logged))
        self.assertEqual(captured["kwargs"]["confirm_fn"]("ignored"), False)
        self.assertEqual(self.app._active_routine_name, "haul")
        self.assertEqual(self.app._haul_stats.commodity, "Aluminium")
        self.assertTrue(self.app._haul_stats.resumed_mid_run)

    def test_haul_dispatch_prompts_to_confirm_unknown_buy_station(self) -> None:
        self.app.query_one = lambda *args, **kwargs: _InputStub()  # type: ignore[method-assign]
        self.app._ship.status = "in_station"
        self.app._ship.station = "Mystery Base"
        self.app._haul_params = {
            "commodity": "Aluminium",
            "buy_station": "",
            "sell_station": "Pawelczyk Dock",
            "sell_system": "Sol",
            "buy_system": "",
            "galaxy_map_settle": "",
            "dock_timeout": "",
        }

        journal_file = Path(self.tmpdir.name) / "Journal.240101000000.01.log"
        journal_file.write_text(
            json.dumps({"event": "Docked", "StationName": "Mystery Base", "StarSystem": "Sol"}) + "\n",
            encoding="utf-8",
        )
        (Path(self.tmpdir.name) / "Cargo.json").write_text(json.dumps({"Inventory": []}), encoding="utf-8")

        self.app._dispatch_haul_loop()

        self.assertEqual(self.app._haul_confirm_buy_station, "Mystery Base")
        self.assertIn("Assume current station", "\n".join(self.app.logged))

    def test_haul_confirm_yes_sets_buy_station_and_starts(self) -> None:
        captured: dict[str, object] = {}
        self.app.query_one = lambda *args, **kwargs: _InputStub()  # type: ignore[method-assign]

        self.app._haul_params = {
            "commodity": "Aluminium",
            "buy_station": "",
            "sell_station": "Pawelczyk Dock",
            "sell_system": "Sol",
            "buy_system": "",
            "galaxy_map_settle": "",
            "dock_timeout": "",
        }
        self.app._controls = object()
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_sleeper = lambda: (lambda _: None)
        self.app._make_watcher = lambda: object()
        self.app._run_in_thread = lambda fn: fn()

        def fake_dispatch() -> None:
            captured["buy_station"] = self.app._haul_params["buy_station"]

        self.app._dispatch_haul_loop = fake_dispatch  # type: ignore[method-assign]
        self.app._haul_confirm_buy_station = "Mystery Base"

        self.app._handle_haul_confirm_prompt("yes")

        self.assertEqual(captured["buy_station"], "Mystery Base")
        self.assertEqual(self.app._haul_confirm_buy_station, "")

    def test_haul_confirm_blank_defaults_to_yes(self) -> None:
        captured: dict[str, object] = {}
        self.app.query_one = lambda *args, **kwargs: _InputStub()  # type: ignore[method-assign]
        self.app._haul_params = {
            "commodity": "Aluminium",
            "buy_station": "",
            "sell_station": "Pawelczyk Dock",
            "sell_system": "Sol",
            "buy_system": "",
            "galaxy_map_settle": "",
            "dock_timeout": "",
        }

        def fake_dispatch() -> None:
            captured["buy_station"] = self.app._haul_params["buy_station"]

        self.app._dispatch_haul_loop = fake_dispatch  # type: ignore[method-assign]
        self.app._haul_confirm_buy_station = "Mystery Base"

        self.app._handle_haul_confirm_prompt("")

        self.assertEqual(captured["buy_station"], "Mystery Base")
        self.assertEqual(self.app._haul_confirm_buy_station, "")

    def test_haul_confirm_no_cancels_launch(self) -> None:
        self.app.query_one = lambda *args, **kwargs: _InputStub()  # type: ignore[method-assign]
        self.app._haul_confirm_buy_station = "Mystery Base"

        self.app._handle_haul_confirm_prompt("no")

        self.assertEqual(self.app._haul_confirm_buy_station, "")
        self.assertIn("Haul launch cancelled", "\n".join(self.app.logged))

    def test_record_history_entry_trims_to_configured_limit(self) -> None:
        self.app._config = self.app._config.__class__(
            paths=self.app._config.paths,
            controls=self.app._config.controls,
            screen=self.app._config.screen,
            runtime=self.app._config.runtime,
            control_room=ControlRoomConfig(
                state_file=self.app._config.control_room.state_file,
                history_limit=2,
            ),
        )

        self.app._record_history_entry(CommandHistoryEntry(raw="dock", command="dock", timestamp="1"))
        self.app._record_history_entry(CommandHistoryEntry(raw="jump", command="jump", timestamp="2"))
        self.app._record_history_entry(CommandHistoryEntry(raw="undock", command="undock", timestamp="3"))

        self.assertEqual([entry.raw for entry in self.app._saved_state.history], ["jump", "undock"])
        self.assertEqual(self.app._history, ["jump", "undock"])

    def test_saved_haul_defaults_use_explicit_default_haul(self) -> None:
        self.app._saved_state.default_haul = {
            "commodity": "Aluminium",
            "buy_station": "Hutton Orbital",
            "galaxy_map_settle": "5.0",
        }
        self.app._ship.station = "Jameson Memorial"
        self.app._ship.system = "Shinrarta Dezhra"

        defaults = self.app._saved_haul_defaults()

        self.assertEqual(defaults["commodity"], "Aluminium")
        self.assertEqual(defaults["buy_station"], "Hutton Orbital")
        self.assertEqual(defaults["sell_station"], "Jameson Memorial")
        self.assertEqual(defaults["sell_system"], "Shinrarta Dezhra")
        self.assertEqual(defaults["galaxy_map_settle"], "5.0")

    def test_filtered_resume_entries_uses_prefix_match(self) -> None:
        self.app._saved_state.history = [
            CommandHistoryEntry(raw="dock", command="dock", timestamp="1"),
            CommandHistoryEntry(raw="dest Sol", command="dest", timestamp="2"),
            CommandHistoryEntry(raw="dest Colonia", command="dest", timestamp="3"),
            CommandHistoryEntry(raw="sell Aluminium", command="sell", timestamp="4"),
        ]

        self.app._resume_filter = "dest "
        labels = [item.label for item in self.app._filtered_resume_entries()]

        self.assertEqual(len(labels), 2)
        self.assertIn("dest Colonia", labels[0])
        self.assertIn("dest Sol", labels[1])

    def test_filtered_resume_entries_empty_filter_returns_full_history(self) -> None:
        self.app._saved_state.history = [
            CommandHistoryEntry(raw="dock", command="dock", timestamp="1"),
            CommandHistoryEntry(raw="jump", command="jump", timestamp="2"),
        ]

        self.app._resume_filter = ""
        raws = [item.entry.raw for item in self.app._filtered_resume_entries()]

        self.assertEqual(raws, ["jump", "dock"])

    def test_log_lines_use_fold_wrap(self) -> None:
        line = _build_log_text("A" * 200)

        self.assertFalse(line.no_wrap)
        self.assertEqual(line.overflow, "fold")

    def test_cargo_summary_lines_limits_to_top_three(self) -> None:
        lines = _cargo_summary_lines([
            {"Name": "gold", "Name_Localised": "Gold", "Count": 4},
            {"Name": "silver", "Name_Localised": "Silver", "Count": 10},
            {"Name": "palladium", "Name_Localised": "Palladium", "Count": 6},
            {"Name": "bertrandite", "Name_Localised": "Bertrandite", "Count": 2},
        ])

        self.assertEqual(lines, [
            "10t Silver",
            "6t Palladium",
            "4t Gold",
        ])

    def test_haul_stats_track_clean_cycle_profit_and_time(self) -> None:
        self.app._ship.status = "in_station"
        self.app._ship.station = "Pawelczyk Dock"
        self.app._ship.credits = 1_000_000
        self.app._time_fn = lambda: 100.0
        self.app._start_haul_stats(
            commodity="Aluminium",
            buy_station="Hutton Orbital",
            sell_station="Pawelczyk Dock",
        )

        self.assertTrue(self.app._haul_stats.waiting_for_sell_departure)
        self.assertEqual(self.app._haul_stats.current_run_started_at, 100.0)

        self.app._time_fn = lambda: 110.0
        self.app._handle_haul_event({"event": "Undocked"}, station_before="Pawelczyk Dock")
        self.assertTrue(self.app._haul_stats.clean_run_active)
        self.assertEqual(self.app._haul_stats.current_run_started_at, 100.0)

        self.app._time_fn = lambda: 200.0
        self.app._handle_haul_event({"event": "MarketBuy", "TotalCost": 250_000}, station_before="Hutton Orbital")
        self.assertEqual(self.app._haul_stats.current_run_profit, -250_000)

        self.app._time_fn = lambda: 310.0
        self.app._handle_haul_event({"event": "Docked", "StationName": "Pawelczyk Dock"}, station_before=None)
        self.assertTrue(self.app._haul_stats.docked_back_at_sell)
        self.assertEqual(self.app._haul_stats.current_run_elapsed_s, 210.0)

        self.app._time_fn = lambda: 315.0
        self.app._handle_haul_event({"event": "MarketSell", "TotalSale": 400_000}, station_before="Pawelczyk Dock")
        self.assertEqual(self.app._haul_stats.current_run_profit, 150_000)

        self.app._time_fn = lambda: 320.0
        self.app._handle_haul_event({"event": "Undocked"}, station_before="Pawelczyk Dock")
        self.assertEqual(self.app._haul_stats.completed_runs, 1)
        self.assertEqual(self.app._haul_stats.last_run_profit, 150_000)
        self.assertEqual(self.app._haul_stats.accumulated_profit, 150_000)
        self.assertEqual(self.app._haul_stats.last_run_elapsed_s, 210.0)
        self.assertEqual(self.app._haul_stats.current_run_started_at, 320.0)

    def test_haul_stats_ignore_partial_resume_until_next_clean_departure(self) -> None:
        self.app._ship.status = "in_supercruise"
        self.app._time_fn = lambda: 50.0
        self.app._start_haul_stats(
            commodity="Aluminium",
            buy_station="Hutton Orbital",
            sell_station="Pawelczyk Dock",
        )

        self.assertTrue(self.app._haul_stats.resumed_mid_run)
        self.assertEqual(self.app._haul_stats.current_run_started_at, 50.0)

        self.app._time_fn = lambda: 200.0
        self.app._handle_haul_event({"event": "MarketSell", "TotalSale": 400_000}, station_before="Pawelczyk Dock")
        self.assertEqual(self.app._haul_stats.current_run_profit, 0)

        self.app._handle_haul_event({"event": "Docked", "StationName": "Pawelczyk Dock"}, station_before=None)
        self.assertTrue(self.app._haul_stats.waiting_for_sell_departure)
        self.assertFalse(self.app._haul_stats.clean_run_active)
        self.assertEqual(self.app._haul_stats.current_run_elapsed_s, 150.0)
        self.assertEqual(self.app._haul_stats.completed_runs, 0)


class ControlRoomDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.app = _HarnessApp(_make_context(Path(self.tmpdir.name)))

    def _last_history(self) -> CommandHistoryEntry | None:
        history = self.app._saved_state.history
        return history[-1] if history else None

    def test_unknown_verb_logs_warning_and_does_not_record_history(self) -> None:
        self.app._dispatch_command("frobnicate now")

        output = "\n".join(self.app.logged)
        self.assertIn("Unknown command: frobnicate now", output)
        self.assertEqual(self.app._saved_state.history, [])

    def test_verb_routing_is_case_insensitive(self) -> None:
        self.app._dispatch_command("HELP set_dest")

        output = "\n".join(self.app.logged)
        self.assertIn("dest <system>", output)
        entry = self._last_history()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.command, "help")

    def test_history_alias_opens_replay_picker(self) -> None:
        self.app._saved_state.history = [
            CommandHistoryEntry(raw="dock", command="dock", timestamp="1"),
        ]

        self.app._dispatch_command("history")

        self.assertTrue(self.app._resume_open)
        entry = self._last_history()
        self.assertEqual(entry.command, "replay")

    def test_exit_alias_requests_shutdown(self) -> None:
        self.app._dispatch_command("exit")

        self.assertTrue(self.app._shutdown_requested)
        entry = self._last_history()
        self.assertEqual(entry.command, "quit")
        self.assertEqual(entry.raw, "exit")

    def test_verbose_on_toggles_state_and_records_history(self) -> None:
        self.app._dispatch_command("verbose on")

        self.assertTrue(self.app._verbose_controls)
        entry = self._last_history()
        self.assertEqual(entry.command, "verbose")
        self.assertEqual(entry.params, {"value": "on"})

    def test_market_filter_sets_filter_and_records_raw_value(self) -> None:
        self.app._dispatch_command("market filter Aluminium")

        self.assertEqual(self.app._market_filter, "Aluminium")
        entry = self._last_history()
        self.assertEqual(entry.command, "market")
        self.assertEqual(entry.params, {"value": "filter Aluminium"})


class ControlRoomEventReducerTests(unittest.TestCase):
    def test_undocked_waits_for_no_track_before_clearing_station(self) -> None:
        ship = ShipState(system="HIP 58412", station="Pawelczyk Dock", status="in_station")

        apply_ship_event(ship, {"event": "Undocked", "StationName": "Pawelczyk Dock"})

        self.assertEqual(ship.status, "in_undocking")
        self.assertEqual(ship.station, "Pawelczyk Dock")

        apply_ship_event(ship, {"event": "Music", "MusicTrack": "DockingComputer"})

        self.assertEqual(ship.status, "in_undocking")
        self.assertEqual(ship.station, "Pawelczyk Dock")

        apply_ship_event(ship, {"event": "Music", "MusicTrack": "NoTrack"})

        self.assertEqual(ship.status, "in_space")
        self.assertIsNone(ship.station)


if __name__ == "__main__":
    unittest.main()
