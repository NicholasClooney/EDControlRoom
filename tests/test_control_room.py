from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from control_room import ControlRoomApp
from edap.config import (
    AppConfig,
    CaptureConfig,
    CaptureRegionConfig,
    ControlsConfig,
    PathsConfig,
    RuntimeConfig,
    ScreenConfig,
)
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


if __name__ == "__main__":
    unittest.main()
