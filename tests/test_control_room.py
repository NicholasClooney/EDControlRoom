from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from control_room import ControlRoomApp, _ALL_ROUTINE_ACTIONS
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

    def _show_resume_picker(self) -> None:  # type: ignore[override]
        if not self._saved_state.history:
            self._log("[dim]No saved command history yet.[/]")
            return
        self._resume_open = True
        self._resume_entries = self._filtered_resume_entries()


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

        with patch("control_room.undock", new=fake_undock):
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

        with patch("control_room.escape_mass_lock", new=fake_escape_mass_lock):
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

        with patch("control_room.market_sell", new=fake_market_sell):
            self.app._sell_all()

        output = "\n".join(self.app.logged)
        self.assertEqual(captured_targets, ["Aluminium"])
        self.assertIn("Cargo.json fallback", output)
        self.assertIn("Sell-all complete", output)
        self.assertNotIn("Nothing sellable in cargo", output)

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


if __name__ == "__main__":
    unittest.main()
