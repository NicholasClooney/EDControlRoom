from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from control_room import ControlRoomApp
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


class ControlRoomCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.app = _HarnessApp(_make_context(Path(self.tmpdir.name)))

    def test_commands_lists_supported_commands(self) -> None:
        self.app._dispatch_command("commands")

        output = "\n".join(self.app.logged)
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

        self.assertEqual(self.app.logged, ["[red]Unknown help topic: mystery[/]"])

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

        self.app._clear_routine()

        self.assertEqual(self.app.exit_calls, 0)

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


if __name__ == "__main__":
    unittest.main()
