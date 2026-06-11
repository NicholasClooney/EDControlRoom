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
from edap.binding_lookup import build_binding_lookup
from edap.config import (
    AppConfig,
    CaptureConfig,
    CaptureRegionConfig,
    ControlRoomConfig,
    ControlsConfig,
    PathsConfig,
    RuntimeConfig,
    ScreenConfig,
    TTSConfig,
)
from edap.control_room.app import ActivityLog, _JOURNAL_ARTIFACT_LOG_FLUSH_EVERY
from edap.control_room.failure_messages import describe_routine_failure
from edap.control_room.events import apply_ship_event
from edap.control_room import rendering as control_room_rendering
from edap.control_room.models import MarketData, ShipState
from edap.control_room_state import CommandHistoryEntry
from edap.routines import RoutineResult
from edap.runtime import ResolvedPath, RuntimeContext
from edap.tts import AnnouncementId
from edap.control_room.workers import PendingRoutineCancelled, RoutineCancelled, run_routine_thread
from edap.version import GitHubRelease


def _make_config(journal_dir: Path, *, activity_log_max_lines: int = 2000) -> AppConfig:
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
            dock_supercruise_exit_settle_seconds=3.0,
            haul_dock_timeout_seconds=600.0,
            undock_timeout_seconds=30.0,
            undock_no_track_timeout_seconds=600.0,
            mass_lock_boost_delay_seconds=5.0,
            market_nav_delay_seconds=0.1,
            market_trade_max_attempts=3,
            market_buy_hold_seconds_per_ton=0.01,
            market_critical_level_multiplier=10.0,
            haul_post_sell_settle_seconds=2.0,
            haul_two_way_auto_hyperspace_engage=True,
            haul_two_way_open_nav_panel_after_hyperspace_arrival=True,
            haul_two_way_nav_panel_open_delay_seconds=3.0,
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
            activity_log_max_lines=activity_log_max_lines,
            command_delay_seconds=0.0,
            status_refresh_seconds=2.0,
        ),
        tts=TTSConfig(enabled=False, title="captain", disabled_messages=(), phrases={}),
    )


def _make_context(
    journal_dir: Path,
    *,
    activity_log_max_lines: int = 2000,
) -> RuntimeContext:
    resolved = ResolvedPath(
        configured={"path": str(journal_dir), "status": "ok", "reason": "test journal dir"},
        auto_detected={"path": str(journal_dir), "status": "ok", "reason": "test journal dir"},
        effective={"path": str(journal_dir), "status": "ok", "source": "configured", "reason": "test journal dir"},
    )
    return RuntimeContext(
        config=_make_config(
            journal_dir,
            activity_log_max_lines=activity_log_max_lines,
        ),
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


class _FakeVersionSource:
    def __init__(
        self,
        *,
        current_version: str = "9.9.9",
        latest_release: GitHubRelease | None = None,
    ) -> None:
        self.current_version = current_version
        self.latest_release = latest_release

    def get_current_version(self) -> str:
        return self.current_version

    def fetch_latest_github_release(self) -> GitHubRelease | None:
        return self.latest_release


class _HarnessApp(ControlRoomApp):
    def __init__(self, ctx: RuntimeContext, *, activity_log_max_lines: int | None = None) -> None:
        self.version_source = _FakeVersionSource()
        super().__init__(
            ctx,
            activity_log_max_lines=activity_log_max_lines,
            version_source=self.version_source,
        )
        self._journal_artifact_log_path = ctx.config.control_room.state_file.parent / "control-room-artifact.log"
        self.logged: list[str] = []
        self.exit_calls = 0

    def _log(self, msg: str) -> None:
        self.logged.append(msg)

    def call_from_thread(self, callback, *args, **kwargs):  # type: ignore[override]
        return callback(*args, **kwargs)

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

    def _refresh_status(self) -> None:  # type: ignore[override]
        return None

    def _show_resume_picker(self) -> None:  # type: ignore[override]
        if not self._saved_state.history:
            self._log("[dim]No saved command history yet.[/]")
            return
        self._resume_open = True
        self._resume_entries = self._filtered_resume_entries()


class _WorkerGroupStub:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str]] = []

    def cancel_group(self, app, group: str) -> None:
        self.calls.append((app, group))


class _ShutdownHarnessApp(ControlRoomApp):
    def __init__(self, ctx: RuntimeContext) -> None:
        self.version_source = _FakeVersionSource()
        super().__init__(ctx, version_source=self.version_source)
        self._journal_artifact_log_path = ctx.config.control_room.state_file.parent / "control-room-artifact.log"
        self.exit_calls = 0

    def exit(self, result=None, return_code: int = 0, message=None) -> None:
        self.exit_calls += 1

    def _finalize_shutdown(self) -> None:
        if self._shutdown_finalized:
            return
        self._shutdown_finalized = True
        if self._journal_artifact_log_handle is not None:
            self._flush_journal_artifact_log()
            self._journal_artifact_log_handle.close()
            self._journal_artifact_log_handle = None
            self._journal_artifact_log_pending_writes = 0
        self._tts.close()
        self.exit()


class _InputStub:
    def __init__(self) -> None:
        self.placeholder = ""
        self.value = ""
        self.cursor_position = 0


class _ActivityLogStub:
    def __init__(self, *, scroll_y: float = 0.0, max_scroll_y: float = 0.0) -> None:
        self.border_title = ""
        self.scroll_y = scroll_y
        self.max_scroll_y = max_scroll_y
        self.auto_scroll = True
        self.writes: list[dict[str, object]] = []

    @property
    def auto_follow_paused(self) -> bool:
        return not self.auto_scroll

    def write(self, content, **kwargs) -> None:
        self.writes.append({"content": content, **kwargs})


class _TimerStub:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _HarnessActivityLog(ActivityLog):
    def __init__(self, *, max_scroll_y: float, **kwargs) -> None:
        super().__init__(**kwargs)
        self._test_max_scroll_y = max_scroll_y

    @property
    def max_scroll_y(self) -> float:
        return self._test_max_scroll_y


class _FakeTTS:
    def __init__(self) -> None:
        self.calls: list[tuple[AnnouncementId, dict[str, object]]] = []
        self.commander_name: str | None = None

    def announce(self, message_id: AnnouncementId, **values: object) -> None:
        self.calls.append((message_id, values))

    def set_commander_name(self, name: str | None) -> None:
        self.commander_name = name

    def close(self) -> None:
        return None


class _ArtifactLogHandleStub:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.flush_calls = 0
        self.close_calls = 0
        self.closed = False

    def write(self, value: str) -> int:
        self.parts.append(value)
        return len(value)

    def flush(self) -> None:
        self.flush_calls += 1

    def close(self) -> None:
        self.close_calls += 1
        self.closed = True

    def getvalue(self) -> str:
        return "".join(self.parts)


class ControlRoomCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.app = _HarnessApp(_make_context(Path(self.tmpdir.name)))
        self.addCleanup(self._close_artifact_log)

    def _close_artifact_log(self) -> None:
        if self.app._journal_artifact_log_handle is not None:
            self.app._journal_artifact_log_handle.close()
            self.app._journal_artifact_log_handle = None

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

    def test_request_quit_on_haul_schedules_stop_after_run(self) -> None:
        worker = _FakeWorker()
        self.app._routine_active = True
        self.app._routine_worker = worker
        self.app._active_routine_name = "haul"
        self.app._tts = _FakeTTS()

        self.app.action_request_quit()

        self.assertFalse(self.app._shutdown_requested)
        self.assertFalse(worker.cancelled)
        self.assertTrue(self.app._haul_stop_requested)
        self.assertIn(
            (AnnouncementId.HAUL_STOP_AFTER_RUN, {}),
            self.app._tts.calls,
        )
        self.assertIn("stop after this run", "\n".join(self.app.logged))

    def test_request_quit_on_haul_cancels_immediately_when_stop_already_pending(self) -> None:
        worker = _FakeWorker()
        self.app._routine_active = True
        self.app._routine_worker = worker
        self.app._active_routine_name = "haul"
        self.app._haul_stop_requested = True

        self.app.action_request_quit()

        self.assertFalse(self.app._shutdown_requested)
        self.assertTrue(worker.cancelled)
        self.assertFalse(self.app._haul_stop_requested)
        self.assertIn("cancelling haul immediately", "\n".join(self.app.logged))

    def test_pending_sigint_cancels_active_routine_without_exiting(self) -> None:
        worker = _FakeWorker()
        self.app._routine_active = True
        self.app._routine_worker = worker

        self.app.request_sigint()
        self.app._drain_pending_sigint()

        self.assertFalse(self.app._sigint_pending)
        self.assertFalse(self.app._shutdown_requested)
        self.assertTrue(worker.cancelled)
        self.assertEqual(self.app.exit_calls, 0)

    def test_pending_sigint_exits_when_idle(self) -> None:
        self.app.request_sigint()

        self.app._drain_pending_sigint()

        self.assertFalse(self.app._sigint_pending)
        self.assertTrue(self.app._shutdown_requested)
        self.assertEqual(self.app.exit_calls, 1)

    def test_bootstrap_ship_state_reads_balance_and_cargo_from_status_json(self) -> None:
        journal_dir = Path(self.tmpdir.name)
        (journal_dir / "Journal.240101000000.01.log").write_text(
            json.dumps({
                "event": "LoadGame",
                "Commander": "VRYAE",
                "Ship": "type6",
                "FuelLevel": 16.0,
                "FuelCapacity": 32.0,
            }) + "\n" + json.dumps({
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
                "Destination": {
                    "System": "Achenar",
                    "Body": "Dawes Hub",
                    "Name": "Dawes Hub",
                },
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

        self.assertEqual(self.app._ship.commander, "VRYAE")
        self.assertEqual(self.app._ship.system, "HIP 58412")
        self.assertEqual(self.app._ship.credits, 123456789)
        self.assertEqual(self.app._ship.cargo_count, 24)
        self.assertEqual(self.app._ship.destination_system, "Achenar")
        self.assertEqual(self.app._ship.destination_body, "Dawes Hub")
        self.assertEqual(self.app._ship.destination_name, "Dawes Hub")
        self.assertEqual(len(self.app._ship.cargo_inventory), 2)

    def test_bootstrap_ship_state_syncs_commander_name_into_tts(self) -> None:
        journal_dir = Path(self.tmpdir.name)
        (journal_dir / "Journal.240101000000.01.log").write_text(
            json.dumps({"event": "LoadGame", "Commander": "VRYAE"}) + "\n",
            encoding="utf-8",
        )
        self.app._tts = _FakeTTS()

        self.app._bootstrap_ship_state()

        self.assertEqual(self.app._tts.commander_name, "VRYAE")

    def test_bootstrap_ship_state_reads_commander_from_commander_event(self) -> None:
        journal_dir = Path(self.tmpdir.name)
        (journal_dir / "Journal.240101000000.01.log").write_text(
            json.dumps({"event": "Commander", "Name": "VRYAE"}) + "\n",
            encoding="utf-8",
        )

        self.app._bootstrap_ship_state()

        self.assertEqual(self.app._ship.commander, "VRYAE")

    def test_sync_status_snapshot_refreshes_destination_without_journal_event(self) -> None:
        journal_dir = Path(self.tmpdir.name)
        (journal_dir / "Status.json").write_text(
            json.dumps({
                "Flags": 0,
                "Destination": {
                    "System": "Shinrarta Dezhra",
                    "Body": "Jameson Memorial",
                    "Name": "Jameson Memorial",
                },
            }),
            encoding="utf-8",
        )

        self.app._sync_status_snapshot()

        self.assertEqual(self.app._ship.destination_system, "Shinrarta Dezhra")
        self.assertEqual(self.app._ship.destination_body, "Jameson Memorial")
        self.assertEqual(self.app._ship.destination_name, "Jameson Memorial")

    def test_status_markup_shows_destination_summary(self) -> None:
        ship = ShipState(
            system="Sol",
            status="in_supercruise",
            destination_system="Achenar",
            destination_body="Dawes Hub",
            destination_name="Dawes Hub",
        )

        markup = control_room_rendering.status_markup(ship)

        self.assertIn("Destination", markup)
        self.assertIn("Achenar / Dawes Hub / Dawes Hub", markup)
        self.assertIn("\n[dim]Destination[/]  [yellow]Achenar / Dawes Hub / Dawes Hub[/]", markup)

    def test_market_markup_shows_zero_demand_sell_rows_with_sell_price(self) -> None:
        market = MarketData(
            station="Pawelczyk Dock",
            system="HIP 58412",
            timestamp="2026-06-08T20:09:46Z",
            items=[
                {
                    "Category": "Foods",
                    "Name": "foodcartridges",
                    "Name_Localised": "Food Cartridges",
                    "Demand": 0,
                    "DemandBracket": 0,
                    "SellPrice": 1929,
                }
            ],
        )

        markup = control_room_rendering.market_markup(market, None)

        self.assertIn("SELL TO MARKET", markup)
        self.assertIn("Food Cartridges", markup)
        self.assertIn("0", markup)
        self.assertIn("1,929", markup)

    def test_market_markup_keeps_sell_rows_plain_name_sorted(self) -> None:
        market = MarketData(
            station="Pawelczyk Dock",
            system="HIP 58412",
            timestamp="2026-06-08T20:09:46Z",
            items=[
                {
                    "Category": "Foods",
                    "Name": "foodcartridges",
                    "Name_Localised": "Food Cartridges",
                    "Demand": 0,
                    "DemandBracket": 0,
                    "SellPrice": 1929,
                },
                {
                    "Category": "Metals",
                    "Name": "gold",
                    "Name_Localised": "Gold",
                    "Demand": 12,
                    "DemandBracket": 1,
                    "SellPrice": 10000,
                },
            ],
        )

        markup = control_room_rendering.market_markup(market, None)

        self.assertLess(markup.index("Food Cartridges"), markup.index("Gold"))

    def test_load_market_json_seeds_ship_station_when_in_station(self) -> None:
        journal_dir = Path(self.tmpdir.name)
        (journal_dir / "Journal.240101000000.01.log").write_text(
            "\n".join(
                [
                    json.dumps({"event": "FSDJump", "StarSystem": "Col 285 Sector HD-F b13-1"}),
                    json.dumps({"event": "Docked", "StationName": "Pawelczyk Dock"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (journal_dir / "Market.json").write_text(
            json.dumps({
                "StationName": "Pawelczyk Dock",
                "StarSystem": "HIP 58412",
                "timestamp": "2026-06-07T21:10:39Z",
                "Items": [],
            }),
            encoding="utf-8",
        )

        self.app._bootstrap_ship_state()
        self.assertEqual(self.app._ship.status, "in_station")
        self.assertEqual(self.app._ship.station, "Pawelczyk Dock")
        self.assertEqual(self.app._ship.system, "Col 285 Sector HD-F b13-1")

        self.app._load_market_json()

        self.assertEqual(self.app._ship.station, "Pawelczyk Dock")
        self.assertEqual(self.app._ship.system, "Col 285 Sector HD-F b13-1")
        self.assertEqual(self.app._market.station, "Pawelczyk Dock")
        self.assertEqual(self.app._market.system, "Col 285 Sector HD-F b13-1")

    def test_load_market_json_does_not_seed_when_not_in_station(self) -> None:
        journal_dir = Path(self.tmpdir.name)
        (journal_dir / "Journal.240101000000.01.log").write_text(
            json.dumps({"event": "SupercruiseEntry"}) + "\n",
            encoding="utf-8",
        )
        (journal_dir / "Market.json").write_text(
            json.dumps({
                "StationName": "Pawelczyk Dock",
                "StarSystem": "HIP 58412",
                "timestamp": "2026-06-07T21:10:39Z",
                "Items": [],
            }),
            encoding="utf-8",
        )

        self.app._bootstrap_ship_state()
        self.app._load_market_json()

        self.assertFalse(self.app._ship.station)

    def test_handle_event_syncs_commander_name_into_tts(self) -> None:
        self.app._tts = _FakeTTS()

        self.app._handle_event({"event": "Commander", "Name": "VRYAE"})

        self.assertEqual(self.app._ship.commander, "VRYAE")
        self.assertEqual(self.app._tts.commander_name, "VRYAE")


class ControlRoomBindingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.app = _HarnessApp(_make_context(Path(self.tmpdir.name)))
        self.addCleanup(self._close_artifact_log)

    def _close_artifact_log(self) -> None:
        if self.app._journal_artifact_log_handle is not None:
            self.app._journal_artifact_log_handle.close()
            self.app._journal_artifact_log_handle = None

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

    def test_dock_command_passes_configured_supercruise_exit_settle(self) -> None:
        captured: dict[str, object] = {}

        self.app._controls = object()
        self.app._ship.status = "supercruise"
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_sleeper = lambda: (lambda _: None)
        self.app._make_watcher = lambda: object()
        self.app._run_in_thread = lambda fn: fn()

        def fake_dock(controls, watcher, **kwargs):
            captured["controls"] = controls
            captured["watcher"] = watcher
            captured["kwargs"] = kwargs
            return None

        with patch("edap.control_room.routines_station.dock", new=fake_dock):
            self.app._cmd_dock()

        self.assertEqual(captured["kwargs"]["supercruise_exit_settle_s"], 3.0)
        self.assertEqual(captured["kwargs"]["step_delay_s"], 0.3)

    def test_buy_command_passes_tts_announcer_to_market_routine(self) -> None:
        captured: dict[str, object] = {}

        self.app._controls = object()
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_sleeper = lambda: (lambda _: None)
        self.app._make_watcher = lambda: object()
        self.app._run_in_thread = lambda fn: fn()

        def fake_market_buy(controls, watcher, **kwargs):
            captured["controls"] = controls
            captured["watcher"] = watcher
            captured["kwargs"] = kwargs
            return None

        with patch("edap.control_room.routines_trade.market_buy", new=fake_market_buy):
            self.app._cmd_buy("aluminium 10")

        announce_fn = captured["kwargs"]["announce_fn"]
        self.assertIs(announce_fn.__self__, self.app)
        self.assertIs(announce_fn.__func__, self.app._announce_tts.__func__)
        self.assertEqual(captured["kwargs"]["buy_hold_seconds_per_ton"], 0.01)
        self.assertEqual(captured["kwargs"]["critical_level_multiplier"], 10.0)

    def test_buy_command_defaults_multi_word_item_to_max(self) -> None:
        captured: dict[str, object] = {}

        self.app._controls = object()
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_sleeper = lambda: (lambda _: None)
        self.app._make_watcher = lambda: object()
        self.app._run_in_thread = lambda fn: fn()

        def fake_market_buy(controls, watcher, **kwargs):
            captured["kwargs"] = kwargs
            return None

        with patch("edap.control_room.routines_trade.market_buy", new=fake_market_buy):
            self.app._cmd_buy("food cartridges")

        self.assertEqual(captured["kwargs"]["target"], "food cartridges")
        self.assertEqual(captured["kwargs"]["amount"], "MAX")

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
        self.app._cmd_boost = lambda **kwargs: called.append("boost")
        self.app._cmd_escape = lambda **kwargs: called.append("escape")

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
            "station_1_buying": "Aluminium",
            "station_1": "Pawelczyk Dock",
            "station_1_system": "Sol",
            "station_2_buying": "Bertrandite",
            "station_2": "Trevithick Dock",
            "station_2_system": "Achenar",
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

        with patch("edap.control_room.routines_haul.haul_loop_two_way", new=fake_haul_loop):
            self.app._dispatch_haul_loop()

        self.assertIn("kwargs", captured)
        self.assertEqual(captured["kwargs"]["undock_timeout_s"], 30.0)
        self.assertEqual(captured["kwargs"]["undock_no_track_timeout_s"], 600.0)
        self.assertFalse(captured["kwargs"]["stop_requested_fn"]())
        self.app._haul_stop_requested = True
        self.assertTrue(captured["kwargs"]["stop_requested_fn"]())
        self.assertIn("Starting haul loop:", "\n".join(self.app.logged))
        self.assertEqual(self.app._active_routine_name, "haul")
        self.assertEqual(self.app._haul_stats.station_1_buying, "Aluminium")
        self.assertEqual(self.app._haul_stats.station_2_buying, "Bertrandite")
        self.assertTrue(self.app._haul_stats.resumed_mid_run)

    def test_haul_dispatch_defaults_station_1_to_current_station(self) -> None:
        captured: dict[str, object] = {}

        self.app._ship.status = "in_station"
        self.app._ship.station = "Mystery Base"
        self.app._ship.system = "Sol"
        self.app._haul_params = {
            "station_1_buying": "Aluminium",
            "station_1": "",
            "station_1_system": "",
            "station_2_buying": "Bertrandite",
            "station_2": "Pawelczyk Dock",
            "station_2_system": "Achenar",
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
            captured["kwargs"] = kwargs
            return RoutineResult(
                action="haul_loop",
                dispatch=ActionDispatchResult(action="haul_loop", status="ok"),
            )

        with patch("edap.control_room.routines_haul.haul_loop_two_way", new=fake_haul_loop):
            self.app._dispatch_haul_loop()

        self.assertEqual(captured["kwargs"]["station_1"], "Mystery Base")
        self.assertEqual(captured["kwargs"]["station_1_system"], "Sol")
        self.assertIn("Station 1 defaulting to current station", "\n".join(self.app.logged))

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
                activity_log_max_lines=self.app._config.control_room.activity_log_max_lines,
                command_delay_seconds=self.app._config.control_room.command_delay_seconds,
            ),
        )

        self.app._record_history_entry(CommandHistoryEntry(raw="dock", command="dock", timestamp="1"))
        self.app._record_history_entry(CommandHistoryEntry(raw="jump", command="jump", timestamp="2"))
        self.app._record_history_entry(CommandHistoryEntry(raw="undock", command="undock", timestamp="3"))

        self.assertEqual([entry.raw for entry in self.app._saved_state.history], ["jump", "undock"])
        self.assertEqual(self.app._history, ["jump", "undock"])

    def test_saved_haul_defaults_use_explicit_default_haul(self) -> None:
        self.app._saved_state.default_haul = {
            "station_1_buying": "Aluminium",
            "station_2": "Hutton Orbital",
            "galaxy_map_settle": "5.0",
        }
        self.app._ship.station = "Jameson Memorial"
        self.app._ship.system = "Shinrarta Dezhra"

        defaults = self.app._saved_haul_defaults()

        self.assertEqual(defaults["station_1_buying"], "Aluminium")
        self.assertEqual(defaults["station_2"], "Hutton Orbital")
        self.assertEqual(defaults["station_1"], "Jameson Memorial")
        self.assertEqual(defaults["station_1_system"], "Shinrarta Dezhra")
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

    def test_activity_log_auto_follows_when_not_paused(self) -> None:
        activity = _ActivityLogStub()
        self.app.query_one = lambda selector, widget_type=None: activity  # type: ignore[method-assign]

        ControlRoomApp._log(self.app, "hello")

        self.assertNotIn("scroll_end", activity.writes[-1])
        self.assertEqual(activity.border_title, "ACTIVITY")

    def test_activity_log_title_reflects_paused_auto_follow(self) -> None:
        activity = _ActivityLogStub()
        self.app.query_one = lambda selector, widget_type=None: activity  # type: ignore[method-assign]
        activity.auto_scroll = False

        self.app._refresh_activity_title()

        self.assertEqual(activity.border_title, "ACTIVITY • AUTO-FOLLOW PAUSED")

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
        self.app._tts = _FakeTTS()
        self.app._ship.status = "in_station"
        self.app._ship.station = "Pawelczyk Dock"
        self.app._ship.credits = 1_000_000
        self.app._time_fn = lambda: 100.0
        self.app._start_haul_stats(
            station_1_buying="Aluminium",
            station_2_buying="Bertrandite",
            station_1="Pawelczyk Dock",
            station_2="Hutton Orbital",
        )

        self.assertTrue(self.app._haul_stats.waiting_for_station_1_departure)
        self.assertEqual(self.app._haul_stats.current_run_started_at, 100.0)

        self.app._handle_haul_event({"event": "MarketBuy", "TotalCost": 100_000}, station_before="Pawelczyk Dock")
        self.assertEqual(self.app._haul_stats.current_run_profit, -100_000)
        self.assertIsNone(self.app._haul_stats.current_run_started_at)

        self.app._time_fn = lambda: 110.0
        self.app._handle_haul_event({"event": "Undocked"}, station_before="Pawelczyk Dock")
        self.assertTrue(self.app._haul_stats.clean_run_active)
        self.assertEqual(self.app._haul_stats.current_run_started_at, 110.0)
        self.assertEqual(self.app._haul_stats.current_run_profit, -100_000)

        self.app._time_fn = lambda: 150.0
        self.app._handle_haul_event({"event": "MarketSell", "TotalSale": 250_000}, station_before="Hutton Orbital")
        self.assertEqual(self.app._haul_stats.current_run_profit, 150_000)

        self.app._time_fn = lambda: 200.0
        self.app._handle_haul_event({"event": "MarketBuy", "TotalCost": 250_000}, station_before="Hutton Orbital")
        self.assertEqual(self.app._haul_stats.current_run_profit, -100_000)

        self.app._time_fn = lambda: 310.0
        self.app._handle_haul_event({"event": "Docked", "StationName": "Pawelczyk Dock"}, station_before=None)
        self.assertTrue(self.app._haul_stats.docked_back_at_station_1)
        self.assertEqual(self.app._haul_stats.current_run_elapsed_s, 200.0)

        self.app._time_fn = lambda: 315.0
        self.app._handle_haul_event({"event": "MarketSell", "TotalSale": 400_000}, station_before="Pawelczyk Dock")
        self.assertEqual(self.app._haul_stats.completed_runs, 1)
        self.assertEqual(self.app._haul_stats.last_run_profit, 300_000)
        self.assertEqual(self.app._haul_stats.accumulated_profit, 300_000)
        self.assertEqual(self.app._haul_stats.last_run_elapsed_s, 200.0)
        self.assertIsNone(self.app._haul_stats.current_run_started_at)
        self.assertTrue(self.app._haul_stats.waiting_for_station_1_departure)
        self.assertIn(
            (AnnouncementId.ROUTE_COMPLETE, {"cycle_count": 1, "total_profit_short": "300 thousand credits"}),
            self.app._tts.calls,
        )

        self.app._time_fn = lambda: 320.0
        self.app._handle_haul_event({"event": "MarketBuy", "TotalCost": 125_000}, station_before="Pawelczyk Dock")
        self.assertEqual(self.app._haul_stats.current_run_profit, -125_000)

        self.app._handle_haul_event({"event": "Undocked"}, station_before="Pawelczyk Dock")
        self.assertTrue(self.app._haul_stats.clean_run_active)
        self.assertEqual(self.app._haul_stats.current_run_started_at, 320.0)
        self.assertEqual(self.app._haul_stats.current_run_profit, -125_000)

    def test_haul_stats_log_ignored_station_1_sell_before_clean_departure(self) -> None:
        self.app._ship.status = "in_station"
        self.app._ship.station = "Pawelczyk Dock"
        self.app._time_fn = lambda: 100.0
        self.app._start_haul_stats(
            station_1_buying="Aluminium",
            station_2_buying="Bertrandite",
            station_1="Pawelczyk Dock",
            station_2="Hutton Orbital",
        )

        self.app._handle_haul_event({"event": "MarketSell", "TotalSale": 400_000}, station_before="Pawelczyk Dock")

        self.assertEqual(self.app._haul_stats.current_run_profit, 0)
        self.assertIn(
            "Ignoring station 1 sale for haul stats (discarding profit from prior run).",
            "\n".join(self.app.logged),
        )

    def test_haul_stats_ignore_partial_resume_until_next_clean_departure(self) -> None:
        self.app._ship.status = "in_supercruise"
        self.app._time_fn = lambda: 50.0
        self.app._start_haul_stats(
            station_1_buying="Aluminium",
            station_2_buying="Bertrandite",
            station_1="Pawelczyk Dock",
            station_2="Hutton Orbital",
        )

        self.assertTrue(self.app._haul_stats.resumed_mid_run)
        self.assertEqual(self.app._haul_stats.current_run_started_at, 50.0)

        self.app._time_fn = lambda: 200.0
        self.app._handle_haul_event({"event": "MarketSell", "TotalSale": 400_000}, station_before="Pawelczyk Dock")
        self.assertEqual(self.app._haul_stats.current_run_profit, 0)

        self.app._handle_haul_event({"event": "Docked", "StationName": "Pawelczyk Dock"}, station_before=None)
        self.assertTrue(self.app._haul_stats.waiting_for_station_1_departure)
        self.assertFalse(self.app._haul_stats.clean_run_active)
        self.assertEqual(self.app._haul_stats.current_run_elapsed_s, 150.0)
        self.assertEqual(self.app._haul_stats.completed_runs, 0)

        self.app._handle_haul_event({"event": "MarketBuy", "TotalCost": 175_000}, station_before="Pawelczyk Dock")
        self.assertEqual(self.app._haul_stats.current_run_profit, -175_000)
        self.assertIsNone(self.app._haul_stats.current_run_started_at)

        self.app._time_fn = lambda: 225.0
        self.app._handle_haul_event({"event": "Undocked"}, station_before="Pawelczyk Dock")
        self.assertTrue(self.app._haul_stats.clean_run_active)
        self.assertEqual(self.app._haul_stats.current_run_started_at, 225.0)
        self.assertEqual(self.app._haul_stats.current_run_profit, -175_000)

    def test_stop_haul_stats_announces_session_summary(self) -> None:
        self.app._tts = _FakeTTS()
        self.app._haul_stats.station_1_buying = "Aluminium"
        self.app._haul_stats.completed_runs = 2
        self.app._haul_stats.accumulated_profit = 1_250_000

        self.app._stop_haul_stats()

        self.assertIn(
            (AnnouncementId.SESSION_COMPLETE, {"cycle_count": 2, "total_profit_short": "1.2 million credits"}),
            self.app._tts.calls,
        )

    def test_handle_event_announces_destination_only(self) -> None:
        self.app._tts = _FakeTTS()

        self.app._handle_event({"event": "FSDTarget", "Name": "Achenar"})

        self.assertIn((AnnouncementId.DESTINATION_SET, {"system_name": "Achenar"}), self.app._tts.calls)

    def test_handle_event_does_not_announce_undocking_outside_haul(self) -> None:
        self.app._tts = _FakeTTS()
        self.app._ship.station = "Pawelczyk Dock"
        self.app._ship.status = "in_station"

        self.app._handle_event({"event": "Undocked", "StationName": "Pawelczyk Dock"})

        self.assertNotIn((AnnouncementId.UNDOCKING, {}), self.app._tts.calls)

    def test_handle_event_announces_undocking_during_active_haul(self) -> None:
        self.app._tts = _FakeTTS()
        self.app._ship.station = "Pawelczyk Dock"
        self.app._ship.status = "in_station"
        self.app._start_haul_stats(
            station_1_buying="Aluminium",
            station_2_buying="Bertrandite",
            station_1="Pawelczyk Dock",
            station_2="Hutton Orbital",
        )

        self.app._handle_event({"event": "Undocked", "StationName": "Pawelczyk Dock"})

        self.assertIn((AnnouncementId.UNDOCKING, {}), self.app._tts.calls)

    def test_handle_event_appends_to_control_room_artifact_log(self) -> None:
        log_path = Path(self.tmpdir.name) / "control-room-artifact.log"
        self.app._journal_artifact_log_path = log_path
        self.app._handle_event({"event": "SupercruiseExit", "Body": "Wells Terminal"})
        if self.app._journal_artifact_log_handle is not None:
            self.app._journal_artifact_log_handle.close()
            self.app._journal_artifact_log_handle = None

        lines = log_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), {"event": "SupercruiseExit", "Body": "Wells Terminal"})

    def test_append_journal_event_defers_flush_until_batch_threshold(self) -> None:
        handle = _ArtifactLogHandleStub()
        self.app._journal_artifact_log_handle = handle

        self.app._append_journal_event({"event": "FSDTarget", "Name": "Achenar"})

        self.assertEqual(handle.flush_calls, 0)
        self.assertEqual(self.app._journal_artifact_log_pending_writes, 1)

        for index in range(_JOURNAL_ARTIFACT_LOG_FLUSH_EVERY - 1):
            self.app._append_journal_event({"event": "Scan", "BodyName": f"Body {index}"})

        self.assertEqual(handle.flush_calls, 1)
        self.assertEqual(self.app._journal_artifact_log_pending_writes, 0)

    def test_finalize_shutdown_flushes_pending_control_room_artifact_log_writes(self) -> None:
        app = _ShutdownHarnessApp(_make_context(Path(self.tmpdir.name)))
        app._tts = _FakeTTS()
        handle = _ArtifactLogHandleStub()
        app._journal_artifact_log_handle = handle
        app._journal_artifact_log_pending_writes = 2

        app._finalize_shutdown()

        self.assertEqual(handle.flush_calls, 1)
        self.assertEqual(handle.close_calls, 1)
        self.assertTrue(handle.closed)
        self.assertEqual(app.exit_calls, 1)
        self.assertEqual(app._journal_artifact_log_pending_writes, 0)

    def test_finalize_shutdown_closes_control_room_artifact_log(self) -> None:
        app = _ShutdownHarnessApp(_make_context(Path(self.tmpdir.name)))
        app._tts = _FakeTTS()
        app._journal_artifact_log_path = Path(self.tmpdir.name) / "control-room-artifact.log"

        app._append_journal_event({"event": "FSDTarget", "Name": "Achenar"})
        handle = app._journal_artifact_log_handle

        self.assertIsNotNone(handle)
        self.assertFalse(handle.closed)

        app._finalize_shutdown()

        self.assertIsNone(app._journal_artifact_log_handle)
        self.assertTrue(handle.closed)
        self.assertEqual(app.exit_calls, 1)


class ActivityLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_activity_log_accepts_explicit_max_lines(self) -> None:
        activity = ActivityLog(max_lines=17)

        self.assertEqual(activity.max_lines, 17)

    def test_control_room_defaults_activity_log_max_lines_from_config(self) -> None:
        app = ControlRoomApp(
            _make_context(Path(self.tmpdir.name), activity_log_max_lines=17)
        )

        self.assertEqual(app._activity_log_max_lines, 17)

    def test_control_room_injected_max_lines_override_config(self) -> None:
        app = ControlRoomApp(
            _make_context(Path(self.tmpdir.name), activity_log_max_lines=17),
            activity_log_max_lines=5,
        )

        self.assertEqual(app._activity_log_max_lines, 5)

    def test_manual_scroll_pauses_auto_follow_for_ten_seconds(self) -> None:
        timer = _TimerStub()
        changes: list[bool] = []
        activity = _HarnessActivityLog(max_scroll_y=10.0, on_pause_changed=changes.append)
        activity.set_timer = lambda delay, callback, *args, **kwargs: timer  # type: ignore[method-assign]
        activity.scroll_y = 4.0

        activity.sync_auto_follow_to_scroll_position()

        self.assertFalse(activity.auto_scroll)
        self.assertEqual(changes, [True])
        self.assertIs(activity._resume_timer, timer)

    def test_reaching_bottom_resumes_auto_follow_immediately(self) -> None:
        changes: list[bool] = []
        activity = _HarnessActivityLog(max_scroll_y=10.0, on_pause_changed=changes.append)
        activity.auto_scroll = False
        activity._resume_timer = _TimerStub()
        activity.scroll_y = 10.0

        activity.sync_auto_follow_to_scroll_position()

        self.assertTrue(activity.auto_scroll)
        self.assertEqual(changes, [False])
        self.assertIsNone(activity._resume_timer)

    def test_pause_resets_existing_resume_timer(self) -> None:
        first_timer = _TimerStub()
        second_timer = _TimerStub()
        activity = _HarnessActivityLog(max_scroll_y=10.0)
        timers = iter([first_timer, second_timer])
        activity.set_timer = lambda delay, callback, *args, **kwargs: next(timers)  # type: ignore[method-assign]
        activity.scroll_y = 4.0

        activity.sync_auto_follow_to_scroll_position()
        activity.sync_auto_follow_to_scroll_position()

        self.assertTrue(first_timer.stopped)
        self.assertIs(activity._resume_timer, second_timer)


class ControlRoomDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.app = _HarnessApp(_make_context(Path(self.tmpdir.name)))
        self.addCleanup(self._close_artifact_log)

    def _close_artifact_log(self) -> None:
        if self.app._journal_artifact_log_handle is not None:
            self.app._journal_artifact_log_handle.close()
            self.app._journal_artifact_log_handle = None

    def _last_history(self) -> CommandHistoryEntry | None:
        history = self.app._saved_state.history
        return history[-1] if history else None

    def test_unknown_verb_logs_warning_and_records_history(self) -> None:
        self.app._dispatch_command("frobnicate now")

        output = "\n".join(self.app.logged)
        self.assertIn("Unknown command: frobnicate now", output)
        entry = self._last_history()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.command, "frobnicate")
        self.assertEqual(entry.raw, "frobnicate now")
        self.assertEqual(entry.params, {"value": "now"})

    def test_invalid_buy_amount_records_history(self) -> None:
        self.app._controls = object()
        self.app._dispatch_command("buy aluminium 0")

        output = "\n".join(self.app.logged)
        self.assertIn("Invalid amount", output)
        entry = self._last_history()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.command, "buy")
        self.assertEqual(entry.raw, "buy aluminium 0")
        self.assertEqual(entry.params, {"target": "aluminium", "amount": None})

    def test_buy_multi_word_item_records_full_target_and_defaults_to_max(self) -> None:
        self.app._controls = object()
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_sleeper = lambda: (lambda _: None)
        self.app._make_watcher = lambda: object()
        self.app._run_in_thread = lambda fn: fn()

        captured: dict[str, object] = {}

        def fake_market_buy(controls, watcher, **kwargs):
            captured["kwargs"] = kwargs
            return None

        with patch("edap.control_room.routines_trade.market_buy", new=fake_market_buy):
            self.app._dispatch_command("buy food cartridges")

        entry = self._last_history()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.command, "buy")
        self.assertEqual(entry.raw, "buy food cartridges")
        self.assertEqual(entry.params, {"target": "food cartridges", "amount": "MAX"})
        self.assertEqual(captured["kwargs"]["target"], "food cartridges")
        self.assertEqual(captured["kwargs"]["amount"], "MAX")

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

    def test_instant_toggle_flips_runtime_mode_and_records_history(self) -> None:
        self.app._dispatch_command("instant")

        self.assertTrue(self.app._instant_mode)
        self.assertTrue(self.app._saved_state.instant_mode)
        entry = self._last_history()
        self.assertEqual(entry.command, "instant")
        self.assertEqual(entry.params, {"value": ""})
        self.assertIn("Instant mode on", "\n".join(self.app.logged))

    def test_instant_off_restores_configured_delay(self) -> None:
        self.app._instant_mode = True

        self.app._dispatch_command("instant off")

        self.assertFalse(self.app._instant_mode)
        self.assertFalse(self.app._saved_state.instant_mode)
        self.assertIn("Instant mode off", "\n".join(self.app.logged))

    def test_load_saved_state_restores_persisted_instant_mode(self) -> None:
        self.app._instant_mode = True
        self.app._save_saved_state()
        self.app._instant_mode = False

        self.app._load_saved_state()

        self.assertTrue(self.app._instant_mode)

    def test_log_startup_modes_reports_instant_mode_state(self) -> None:
        self.app._instant_mode = True

        self.app._log_startup_modes()

        self.assertIn("Instant mode on — control with: instant", "\n".join(self.app.logged))

    def test_log_current_version_reports_current_version(self) -> None:
        self.app._current_version = "1.7.1"

        self.app._log_current_version(is_latest=None)

        self.assertIn("Currently running version *v1.7.1* of EDControlRoom", "\n".join(self.app.logged))

    def test_log_current_version_reports_latest_version(self) -> None:
        self.app._current_version = "1.7.1"

        self.app._log_current_version(is_latest=True)

        self.assertIn(
            "Currently running latest version (*v1.7.1*) of EDControlRoom",
            "\n".join(self.app.logged),
        )

    def test_start_update_check_skips_when_disabled(self) -> None:
        self.app._config = AppConfig(
            paths=self.app._config.paths,
            controls=self.app._config.controls,
            screen=self.app._config.screen,
            runtime=self.app._config.runtime,
            control_room=ControlRoomConfig(
                state_file=self.app._config.control_room.state_file,
                history_limit=self.app._config.control_room.history_limit,
                activity_log_max_lines=self.app._config.control_room.activity_log_max_lines,
                command_delay_seconds=self.app._config.control_room.command_delay_seconds,
                status_refresh_seconds=self.app._config.control_room.status_refresh_seconds,
                check_for_updates=False,
            ),
            tts=self.app._config.tts,
        )

        with patch.object(self.app, "_check_for_updates") as mock_check:
            self.app._start_update_check()

        mock_check.assert_not_called()
        self.assertIn(
            "Currently running version *v9.9.9* of EDControlRoom",
            "\n".join(self.app.logged),
        )

    def test_log_update_available_reports_newer_release(self) -> None:
        self.app._current_version = "1.7.1"

        self.app._log_update_available(
            GitHubRelease(
                tag_name="v1.8.0",
                name="",
                html_url="https://github.com/TheClooneyCollection/EDControlRoom/releases/tag/v1.8.0",
                published_at="2026-06-10T00:00:00Z",
            )
        )

        output = "\n".join(self.app.logged)
        self.assertIn("A newer EDControlRoom release is available: v1.8.0", output)
        self.assertIn("Currently running version *v1.7.1* of EDControlRoom", output)
        self.assertIn("releases/tag/v1.8.0", output)

    def test_log_bindings_status_reports_effective_bindings_file(self) -> None:
        bindings_path = Path(self.tmpdir.name) / "Custom.binds"
        resolved = ResolvedPath(
            configured={"path": str(bindings_path), "status": "ok", "reason": "test bindings file"},
            auto_detected={"path": str(bindings_path), "status": "ok", "reason": "test bindings file"},
            effective={
                "path": str(bindings_path),
                "status": "ok",
                "source": "configured",
                "reason": "test bindings file",
            },
        )
        self.app._ctx = RuntimeContext(
            config=self.app._ctx.config,
            game_paths=None,
            journal=self.app._ctx.journal,
            bindings=resolved,
            input_controller=None,
            screen_capture=None,
            binding_lookup=build_binding_lookup(bindings={}, actions=[]),
        )

        self.app._log_bindings_status()

        output = "\n".join(self.app.logged)
        self.assertIn(f"Bindings file: {bindings_path}", output)
        self.assertIn("source: configured", output)

    def test_log_bindings_status_warns_about_missing_mappings(self) -> None:
        bindings_path = Path(self.tmpdir.name) / "Custom.binds"
        resolved = ResolvedPath(
            configured={"path": str(bindings_path), "status": "ok", "reason": "test bindings file"},
            auto_detected={"path": str(bindings_path), "status": "ok", "reason": "test bindings file"},
            effective={
                "path": str(bindings_path),
                "status": "ok",
                "source": "configured",
                "reason": "test bindings file",
            },
        )
        lookup = build_binding_lookup(bindings={}, actions=["UI_Back", "SetSpeedZero"])
        self.app._ctx = RuntimeContext(
            config=self.app._ctx.config,
            game_paths=None,
            journal=self.app._ctx.journal,
            bindings=resolved,
            input_controller=None,
            screen_capture=None,
            binding_lookup=lookup,
        )

        self.app._log_bindings_status()

        output = "\n".join(self.app.logged)
        self.assertIn("Bindings warning", output)
        self.assertIn("UI_Back -> UI Back (General Controls > Interface Mode)", output)
        self.assertIn(
            "SetSpeedZero -> Set Speed to 0% (Ship Controls > Flight Throttle)",
            output,
        )

    def test_log_bindings_status_reports_joystick_only_binding_reason(self) -> None:
        bindings_path = Path(self.tmpdir.name) / "Custom.binds"
        resolved = ResolvedPath(
            configured={"path": str(bindings_path), "status": "ok", "reason": "test bindings file"},
            auto_detected={"path": str(bindings_path), "status": "ok", "reason": "test bindings file"},
            effective={
                "path": str(bindings_path),
                "status": "ok",
                "source": "configured",
                "reason": "test bindings file",
            },
        )
        lookup = build_binding_lookup(
            bindings={},
            missing_actions={
                "UseBoostJuice": "action has joystick/controller bindings, but none are keyboard bindings",
            },
            actions=["UseBoostJuice"],
        )
        self.app._ctx = RuntimeContext(
            config=self.app._ctx.config,
            game_paths=None,
            journal=self.app._ctx.journal,
            bindings=resolved,
            input_controller=None,
            screen_capture=None,
            binding_lookup=lookup,
        )

        self.app._log_bindings_status()

        output = "\n".join(self.app.logged)
        self.assertIn(
            "UseBoostJuice -> Engine Boost (Ship Controls > Flight Miscellaneous)",
            output,
        )
        self.assertIn("joystick/controller bindings", output)

    def test_log_bindings_status_ignores_unused_maneuver_mappings(self) -> None:
        bindings_path = Path(self.tmpdir.name) / "Custom.binds"
        resolved = ResolvedPath(
            configured={"path": str(bindings_path), "status": "ok", "reason": "test bindings file"},
            auto_detected={"path": str(bindings_path), "status": "ok", "reason": "test bindings file"},
            effective={
                "path": str(bindings_path),
                "status": "ok",
                "source": "configured",
                "reason": "test bindings file",
            },
        )
        lookup = build_binding_lookup(
            bindings={},
            actions=["RollLeftButton", "PitchUpButton", "YawLeftButton"],
        )
        self.app._ctx = RuntimeContext(
            config=self.app._ctx.config,
            game_paths=None,
            journal=self.app._ctx.journal,
            bindings=resolved,
            input_controller=None,
            screen_capture=None,
            binding_lookup=lookup,
        )

        self.app._log_bindings_status()

        output = "\n".join(self.app.logged)
        self.assertNotIn("Bindings warning", output)
        self.assertNotIn("RollLeftButton", output)
        self.assertNotIn("PitchUpButton", output)
        self.assertNotIn("YawLeftButton", output)

    def test_market_filter_sets_filter_and_records_raw_value(self) -> None:
        self.app._dispatch_command("market filter Aluminium")

        self.assertEqual(self.app._market_filter, "Aluminium")
        entry = self._last_history()
        self.assertEqual(entry.command, "market")
        self.assertEqual(entry.params, {"value": "filter Aluminium"})

    def test_typed_executable_command_waits_before_launch(self) -> None:
        delays: list[float] = []
        called: list[str] = []

        self.app._controls = object()
        self.app._config = self.app._config.__class__(
            paths=self.app._config.paths,
            controls=self.app._config.controls,
            screen=self.app._config.screen,
            runtime=self.app._config.runtime,
            control_room=ControlRoomConfig(
                state_file=self.app._config.control_room.state_file,
                history_limit=self.app._config.control_room.history_limit,
                activity_log_max_lines=self.app._config.control_room.activity_log_max_lines,
                command_delay_seconds=5.0,
            ),
        )
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_watcher = lambda: object()
        self.app._make_sleeper = lambda: (lambda delay: delays.append(delay))
        self.app._run_in_thread = lambda fn: fn()

        def fake_jump(controls, watcher, **kwargs):
            called.append("jump")
            return None

        with patch("edap.control_room.routines_movement.jump", new=fake_jump):
            self.app._dispatch_command("jump")

        self.assertEqual(delays, [5.0])
        self.assertEqual(called, ["jump"])
        self.assertIn("Executing jump in 5.0s...", "\n".join(self.app.logged))
        self.assertIn("Starting jump sequence...", "\n".join(self.app.logged))

    def test_bang_prefixed_command_skips_delay_and_preserves_raw_history(self) -> None:
        delays: list[float] = []
        called: list[str] = []

        self.app._controls = object()
        self.app._config = self.app._config.__class__(
            paths=self.app._config.paths,
            controls=self.app._config.controls,
            screen=self.app._config.screen,
            runtime=self.app._config.runtime,
            control_room=ControlRoomConfig(
                state_file=self.app._config.control_room.state_file,
                history_limit=self.app._config.control_room.history_limit,
                activity_log_max_lines=self.app._config.control_room.activity_log_max_lines,
                command_delay_seconds=5.0,
            ),
        )
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_watcher = lambda: object()
        self.app._make_sleeper = lambda: (lambda delay: delays.append(delay))
        self.app._run_in_thread = lambda fn: fn()

        def fake_jump(controls, watcher, **kwargs):
            called.append("jump")
            return None

        with patch("edap.control_room.routines_movement.jump", new=fake_jump):
            self.app._dispatch_command("!jump")

        self.assertEqual(delays, [])
        self.assertEqual(called, ["jump"])
        self.assertEqual(self._last_history().raw, "!jump")  # type: ignore[union-attr]
        self.assertNotIn("Executing jump in 5.0s...", "\n".join(self.app.logged))

    def test_instant_mode_skips_delay_without_bang_prefix(self) -> None:
        delays: list[float] = []
        called: list[str] = []

        self.app._controls = object()
        self.app._instant_mode = True
        self.app._config = self.app._config.__class__(
            paths=self.app._config.paths,
            controls=self.app._config.controls,
            screen=self.app._config.screen,
            runtime=self.app._config.runtime,
            control_room=ControlRoomConfig(
                state_file=self.app._config.control_room.state_file,
                history_limit=self.app._config.control_room.history_limit,
                activity_log_max_lines=self.app._config.control_room.activity_log_max_lines,
                command_delay_seconds=5.0,
            ),
        )
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_watcher = lambda: object()
        self.app._make_sleeper = lambda: (lambda delay: delays.append(delay))
        self.app._run_in_thread = lambda fn: fn()

        def fake_jump(controls, watcher, **kwargs):
            called.append("jump")
            return None

        with patch("edap.control_room.routines_movement.jump", new=fake_jump):
            self.app._dispatch_command("jump")

        self.assertEqual(delays, [])
        self.assertEqual(called, ["jump"])
        self.assertNotIn("Executing jump in 5.0s...", "\n".join(self.app.logged))

    def test_replay_execute_uses_same_command_delay(self) -> None:
        delays: list[float] = []
        called: list[str] = []

        self.app._controls = object()
        self.app._config = self.app._config.__class__(
            paths=self.app._config.paths,
            controls=self.app._config.controls,
            screen=self.app._config.screen,
            runtime=self.app._config.runtime,
            control_room=ControlRoomConfig(
                state_file=self.app._config.control_room.state_file,
                history_limit=self.app._config.control_room.history_limit,
                activity_log_max_lines=self.app._config.control_room.activity_log_max_lines,
                command_delay_seconds=5.0,
            ),
        )
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_watcher = lambda: object()
        self.app._make_sleeper = lambda: (lambda delay: delays.append(delay))
        self.app._run_in_thread = lambda fn: fn()

        def fake_jump(controls, watcher, **kwargs):
            called.append("jump")
            return None

        with patch("edap.control_room.routines_movement.jump", new=fake_jump):
            self.app._replay_history_entry(
                CommandHistoryEntry(raw="jump", command="jump", timestamp="1"),
                edit=False,
            )

        self.assertEqual(delays, [5.0])
        self.assertEqual(called, ["jump"])

    def test_replay_immediate_executes_without_prefixing_saved_history(self) -> None:
        delays: list[float] = []
        called: list[str] = []

        self.app._controls = object()
        self.app._config = self.app._config.__class__(
            paths=self.app._config.paths,
            controls=self.app._config.controls,
            screen=self.app._config.screen,
            runtime=self.app._config.runtime,
            control_room=ControlRoomConfig(
                state_file=self.app._config.control_room.state_file,
                history_limit=self.app._config.control_room.history_limit,
                activity_log_max_lines=self.app._config.control_room.activity_log_max_lines,
                command_delay_seconds=5.0,
            ),
        )
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_watcher = lambda: object()
        self.app._make_sleeper = lambda: (lambda delay: delays.append(delay))
        self.app._run_in_thread = lambda fn: fn()

        def fake_jump(controls, watcher, **kwargs):
            called.append("jump")
            return None

        with patch("edap.control_room.routines_movement.jump", new=fake_jump):
            self.app._replay_history_entry(
                CommandHistoryEntry(raw="jump", command="jump", timestamp="1"),
                edit=False,
                skip_delay=True,
            )

        self.assertEqual(delays, [])
        self.assertEqual(called, ["jump"])
        self.assertEqual(self._last_history().raw, "jump")  # type: ignore[union-attr]

    def test_replay_edit_stays_immediate(self) -> None:
        delays: list[float] = []
        input_stub = _InputStub()
        focused: list[object] = []

        self.app._config = self.app._config.__class__(
            paths=self.app._config.paths,
            controls=self.app._config.controls,
            screen=self.app._config.screen,
            runtime=self.app._config.runtime,
            control_room=ControlRoomConfig(
                state_file=self.app._config.control_room.state_file,
                history_limit=self.app._config.control_room.history_limit,
                activity_log_max_lines=self.app._config.control_room.activity_log_max_lines,
                command_delay_seconds=5.0,
            ),
        )
        self.app._make_sleeper = lambda: (lambda delay: delays.append(delay))
        self.app.query_one = lambda *args, **kwargs: input_stub  # type: ignore[method-assign]
        self.app.set_focus = lambda widget: focused.append(widget)  # type: ignore[method-assign]

        self.app._replay_history_entry(
            CommandHistoryEntry(raw="jump", command="jump", timestamp="1"),
            edit=True,
        )

        self.assertEqual(delays, [])
        self.assertEqual(input_stub.value, "jump")
        self.assertEqual(input_stub.cursor_position, 4)
        self.assertEqual(focused, [input_stub])

    def test_non_executable_command_stays_immediate_even_with_delay_configured(self) -> None:
        delays: list[float] = []

        self.app._config = self.app._config.__class__(
            paths=self.app._config.paths,
            controls=self.app._config.controls,
            screen=self.app._config.screen,
            runtime=self.app._config.runtime,
            control_room=ControlRoomConfig(
                state_file=self.app._config.control_room.state_file,
                history_limit=self.app._config.control_room.history_limit,
                activity_log_max_lines=self.app._config.control_room.activity_log_max_lines,
                command_delay_seconds=5.0,
            ),
        )
        self.app._make_sleeper = lambda: (lambda delay: delays.append(delay))

        self.app._dispatch_command("help dock")

        self.assertEqual(delays, [])
        self.assertIn("dock", "\n".join(self.app.logged))

    def test_cancellation_during_pending_delay_prevents_launch(self) -> None:
        called: list[str] = []

        self.app._controls = object()
        self.app._config = self.app._config.__class__(
            paths=self.app._config.paths,
            controls=self.app._config.controls,
            screen=self.app._config.screen,
            runtime=self.app._config.runtime,
            control_room=ControlRoomConfig(
                state_file=self.app._config.control_room.state_file,
                history_limit=self.app._config.control_room.history_limit,
                activity_log_max_lines=self.app._config.control_room.activity_log_max_lines,
                command_delay_seconds=5.0,
            ),
        )
        self.app._make_progress = lambda: (lambda _: None)
        self.app._make_controls = lambda progress: object()
        self.app._make_watcher = lambda: object()
        self.app._make_sleeper = lambda: (lambda delay: (_ for _ in ()).throw(RoutineCancelled()))

        def fake_run_in_thread(fn):
            try:
                return fn()
            except PendingRoutineCancelled as exc:
                self.app._log(f"[yellow]{exc}[/]")
                self.app._clear_routine()
                return None

        self.app._run_in_thread = fake_run_in_thread

        def fake_jump(controls, watcher, **kwargs):
            called.append("jump")
            return None

        with patch("edap.control_room.routines_movement.jump", new=fake_jump):
            self.app._dispatch_command("jump")

        self.assertEqual(called, [])
        self.assertFalse(self.app._routine_active)
        self.assertIn("Cancelled pending jump before execution.", "\n".join(self.app.logged))


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


class ControlRoomFailureMessageTests(unittest.TestCase):
    def test_station_mismatch_includes_edit_guidance(self) -> None:
        result = RoutineResult(
            action="MarketBuy",
            dispatch=ActionDispatchResult(
                action="MarketBuy",
                status="error",
                reason=(
                    "Station check failed after 3 attempts: "
                    "Market.json is from 'Hsulong Orbital' but last Docked event is 'Jameson Memorial'"
                ),
            ),
        )

        message, suggestion = describe_routine_failure(result)

        self.assertIn("Station mismatch", message)
        self.assertIn("Hsulong Orbital", message)
        self.assertIn("Jameson Memorial", message)
        self.assertIn("market data indicates", message)
        self.assertIn("we are docked at", message)
        self.assertIsNotNone(suggestion)
        self.assertIn("Ctrl-R", suggestion or "")
        self.assertIn("press e to edit", suggestion or "")

    def test_route_mismatch_includes_replay_guidance(self) -> None:
        result = RoutineResult(
            action="GalaxyMapOpen",
            dispatch=ActionDispatchResult(
                action="GalaxyMapOpen",
                status="error",
                reason="route mismatch: expected 'Sol', got 'Achenar'",
            ),
        )

        message, suggestion = describe_routine_failure(result)

        self.assertIn("Destination mismatch", message)
        self.assertIn("Sol", message)
        self.assertIn("Achenar", message)
        self.assertIsNotNone(suggestion)
        self.assertIn("Ctrl-R", suggestion or "")

    def test_market_target_mismatch_uses_operator_language(self) -> None:
        result = RoutineResult(
            action="MarketSell",
            dispatch=ActionDispatchResult(
                action="MarketSell",
                status="error",
                reason="'Gold Ore' not found in market list (first items: ['Bertrandite'])",
            ),
        )

        message, suggestion = describe_routine_failure(result)

        self.assertEqual(
            message,
            "Commodity mismatch: Gold Ore was not found in this station's market list.",
        )
        self.assertIsNotNone(suggestion)
        self.assertIn("commodity name", suggestion or "")

    def test_worker_logs_failed_reason_and_try_line(self) -> None:
        app = _HarnessApp(_make_context(Path(tempfile.mkdtemp())))

        class _Worker:
            is_cancelled = False

        result = RoutineResult(
            action="MarketBuy",
            dispatch=ActionDispatchResult(
                action="MarketBuy",
                status="error",
                reason=(
                    "Station check failed after 3 attempts: "
                    "Market.json is from 'Hsulong Orbital' but last Docked event is 'Jameson Memorial'"
                ),
            ),
        )

        with patch("edap.control_room.workers.get_current_worker", return_value=_Worker()):
            run_routine_thread(app, lambda: result)

        joined = "\n".join(app.logged)
        self.assertIn("Failed: MarketBuy -- Station mismatch", joined)
        self.assertIn("Try: Open replay history with Ctrl-R, press e to edit", joined)


if __name__ == "__main__":
    unittest.main()
