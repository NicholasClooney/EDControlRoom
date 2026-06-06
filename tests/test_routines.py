from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from edap.actions import ActionDispatchResult
from edap.binding_lookup import NormalizedBinding
from edap.routines import (
    RoutineResult,
    auto_zero_throttle_on_arrival,
    dock,
    docking_request_sequence,
    jump,
    set_gal_map_destination,
    set_speed_zero_then_wait,
    station_refuel_menu,
    station_refuel_menu_sequence,
)


class FakeShipControls:
    def __init__(
        self,
        *,
        set_speed_zero_result: ActionDispatchResult,
        jump_result: ActionDispatchResult | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._set_speed_zero_result = set_speed_zero_result
        self._jump_result = jump_result or set_speed_zero_result

    def set_speed_zero(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "SetSpeedZero", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def hyper_super_combination(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "HyperSuperCombination", "repeat": repeat, "hold_s": hold_s})
        return self._jump_result

    def ui_up(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "UI_Up", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def ui_select(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "UI_Select", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def ui_down(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "UI_Down", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def focus_left_panel(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "FocusLeftPanel", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def ui_back(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "UI_Back", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def cycle_next_panel(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "CycleNextPanel", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def cycle_previous_panel(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "CyclePreviousPanel", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def boost(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "BoostButton", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def ui_right(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "UI_Right", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def ui_left(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "UI_Left", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def galaxy_map_open(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "GalaxyMapOpen", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def cam_zoom_in(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "CamZoomIn", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result

    def type_text(self, text: str) -> None:
        self.calls.append({"action": "type_text", "text": text})


class FakeWatcher:
    def __init__(self, batches: list[list[dict[str, object]]]) -> None:
        self._batches = list(batches)
        self.poll_calls = 0

    def poll(self) -> list[dict[str, object]]:
        self.poll_calls += 1
        if self._batches:
            return self._batches.pop(0)
        return []


class RoutinesTests(unittest.TestCase):
    def test_set_speed_zero_then_wait_dispatches_and_sleeps(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=
            ActionDispatchResult(
                action="SetSpeedZero",
                status="ok",
                binding=NormalizedBinding(key="x", modifier=None),
                repeat=2,
                hold_s=0.05,
            )
        )
        sleep_calls: list[float] = []

        result = set_speed_zero_then_wait(
            controls,
            repeat=2,
            hold_s=0.05,
            wait_s=1.25,
            sleeper=sleep_calls.append,
        )

        self.assertIsInstance(result, RoutineResult)
        self.assertEqual(result.action, "SetSpeedZero")
        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(controls.calls, [{"action": "SetSpeedZero", "repeat": 2, "hold_s": 0.05}])
        self.assertEqual(sleep_calls, [1.25])

    def test_set_speed_zero_then_wait_skips_sleep_when_wait_is_zero(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=
            ActionDispatchResult(
                action="SetSpeedZero",
                status="ok",
                binding=NormalizedBinding(key="x", modifier=None),
            )
        )
        sleep_calls: list[float] = []

        result = set_speed_zero_then_wait(controls, sleeper=sleep_calls.append)

        self.assertEqual(result.wait_s, 0.0)
        self.assertEqual(controls.calls, [{"action": "SetSpeedZero", "repeat": 1, "hold_s": 0.0}])
        self.assertEqual(sleep_calls, [])

    def test_set_speed_zero_then_wait_skips_sleep_when_dispatch_fails(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=
            ActionDispatchResult(
                action="SetSpeedZero",
                status="missing",
                repeat=1,
                hold_s=0.0,
                reason="binding missing",
            )
        )
        sleep_calls: list[float] = []

        result = set_speed_zero_then_wait(
            controls,
            wait_s=0.5,
            sleeper=sleep_calls.append,
        )

        self.assertEqual(result.dispatch.status, "missing")
        self.assertEqual(sleep_calls, [])

    def test_set_speed_zero_then_wait_rejects_negative_wait(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=
            ActionDispatchResult(
                action="SetSpeedZero",
                status="ok",
                binding=NormalizedBinding(key="x", modifier=None),
            )
        )

        with self.assertRaisesRegex(ValueError, "wait_s must be non-negative"):
            set_speed_zero_then_wait(controls, wait_s=-0.1)

    def test_auto_zero_throttle_on_arrival_dispatches_on_supercruise_exit(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=
            ActionDispatchResult(
                action="SetSpeedZero",
                status="ok",
                binding=NormalizedBinding(key="x", modifier=None),
            )
        )
        events = [
            {"event": "LoadGame"},
            {"event": "SupercruiseEntry"},
            {"event": "SupercruiseExit", "StarSystem": "Achenar"},
        ]

        result = auto_zero_throttle_on_arrival(controls, events, repeat=2, hold_s=0.05)

        self.assertEqual(controls.calls, [{"action": "SetSpeedZero", "repeat": 2, "hold_s": 0.05}])
        self.assertEqual(result.action, "SetSpeedZero")
        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(result.trigger_event, {"event": "SupercruiseExit", "StarSystem": "Achenar"})

    def test_auto_zero_throttle_on_arrival_raises_if_stream_ends_without_event(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=
            ActionDispatchResult(
                action="SetSpeedZero",
                status="ok",
                binding=NormalizedBinding(key="x", modifier=None),
            )
        )

        with self.assertRaisesRegex(RuntimeError, "SupercruiseExit"):
            auto_zero_throttle_on_arrival(controls, [{"event": "LoadGame"}])

        self.assertEqual(controls.calls, [])

    def test_jump_dispatches_fsd_waits_for_supercruise_and_zeroes_throttle(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=ActionDispatchResult(
                action="SetSpeedZero",
                status="ok",
                binding=NormalizedBinding(key="x", modifier=None),
            ),
            jump_result=ActionDispatchResult(
                action="HyperSuperCombination",
                status="ok",
                binding=NormalizedBinding(key="j", modifier="left_shift"),
                hold_s=1.0,
            ),
        )
        watcher = FakeWatcher(
            [
                [{"event": "StartJump", "JumpType": "Hyperspace", "StarClass": "K"}],
                [{"event": "FSDJump", "StarSystem": "Achenar"}],
            ]
        )
        time_values = iter([0.0, 0.0, 0.0, 0.1, 0.1])

        result = jump(
            controls,
            watcher,
            max_retries=3,
            jump_hold_s=1.0,
            start_timeout_s=5.0,
            completion_timeout_s=5.0,
            time_fn=lambda: next(time_values),
        )

        self.assertEqual(
            controls.calls,
            [
                {"action": "HyperSuperCombination", "repeat": 1, "hold_s": 1.0},
                {"action": "SetSpeedZero", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(result.trigger_event, {"event": "FSDJump", "StarSystem": "Achenar"})
        self.assertEqual(result.details["attempt"], 1)

    def test_jump_returns_error_after_retry_budget_exhausted(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=ActionDispatchResult(
                action="SetSpeedZero",
                status="ok",
                binding=NormalizedBinding(key="x", modifier=None),
            ),
            jump_result=ActionDispatchResult(
                action="HyperSuperCombination",
                status="ok",
                binding=NormalizedBinding(key="j", modifier="left_shift"),
                hold_s=1.0,
            ),
        )
        watcher = FakeWatcher([[], []])
        time_values = iter([0.0, 0.2, 0.2, 0.4])

        result = jump(
            controls,
            watcher,
            max_retries=2,
            jump_hold_s=1.0,
            start_timeout_s=0.1,
            completion_timeout_s=0.1,
            time_fn=lambda: next(time_values),
        )

        self.assertEqual(
            controls.calls,
            [
                {"action": "HyperSuperCombination", "repeat": 1, "hold_s": 1.0},
                {"action": "HyperSuperCombination", "repeat": 1, "hold_s": 1.0},
            ],
        )
        self.assertEqual(result.dispatch.status, "error")
        self.assertIn("retry budget", result.dispatch.reason)

    def test_station_refuel_menu_sequence_dispatches_up_select_down(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=ActionDispatchResult(
                action="UI_Up",
                status="ok",
                binding=NormalizedBinding(key="up", modifier=None),
            )
        )
        sleep_calls: list[float] = []

        result = station_refuel_menu_sequence(controls, settle_s=0.5, sleeper=sleep_calls.append)

        self.assertEqual(
            controls.calls,
            [
                {"action": "UI_Up", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Select", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Down", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertEqual(sleep_calls, [0.5, 0.5])
        self.assertEqual(result.action, "UI_Down")
        self.assertEqual(result.dispatch.status, "ok")

    def test_station_refuel_menu_waits_for_docked_then_dispatches_sequence(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=ActionDispatchResult(
                action="UI_Up",
                status="ok",
                binding=NormalizedBinding(key="up", modifier=None),
            )
        )
        watcher = FakeWatcher([[{"event": "Docked", "StationName": "Pawelczyk Dock"}]])
        sleep_calls: list[float] = []
        time_values = iter([0.0, 0.0])

        result = station_refuel_menu(
            controls,
            watcher,
            dock_timeout_s=30.0,
            settle_s=2.0,
            time_fn=lambda: next(time_values),
            sleeper=sleep_calls.append,
        )

        self.assertEqual(result.trigger_event, {"event": "Docked", "StationName": "Pawelczyk Dock"})
        self.assertEqual(
            controls.calls,
            [
                {"action": "UI_Up", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Select", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Down", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertEqual(sleep_calls, [2.0, 0.5, 0.5])

    def test_station_refuel_menu_returns_error_when_docked_not_seen(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=ActionDispatchResult(
                action="UI_Up",
                status="ok",
                binding=NormalizedBinding(key="up", modifier=None),
            )
        )
        watcher = FakeWatcher([[]])
        time_values = iter([0.0, 0.2])

        result = station_refuel_menu(
            controls,
            watcher,
            dock_timeout_s=0.1,
            settle_s=2.0,
            time_fn=lambda: next(time_values),
            sleeper=lambda _: None,
        )

        self.assertEqual(result.dispatch.status, "error")
        self.assertIn("docked event", result.dispatch.reason)

    def test_docking_request_sequence_dispatches_stream_deck_menu_walk(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=ActionDispatchResult(
                action="UI_Select",
                status="ok",
                binding=NormalizedBinding(key="space", modifier=None),
            )
        )
        sleep_calls: list[float] = []

        result = docking_request_sequence(controls, sleeper=sleep_calls.append)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            controls.calls,
            [
                {"action": "UI_Back", "repeat": 10, "hold_s": 0.0},
                {"action": "FocusLeftPanel", "repeat": 1, "hold_s": 0.0},
                {"action": "CycleNextPanel", "repeat": 1, "hold_s": 0.0},
                {"action": "CycleNextPanel", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Right", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Select", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Left", "repeat": 1, "hold_s": 0.0},
                {"action": "CyclePreviousPanel", "repeat": 1, "hold_s": 0.0},
                {"action": "CyclePreviousPanel", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Back", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertEqual(sleep_calls, [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 1.0])

    def test_dock_waits_for_supercruise_exit_and_then_docks(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=ActionDispatchResult(
                action="SetSpeedZero",
                status="ok",
                binding=NormalizedBinding(key="x", modifier=None),
            )
        )
        watcher = FakeWatcher(
            [
                [{"event": "SupercruiseExit", "BodyType": "Station"}],
                [],  # absorbed by prime poll() before the retry loop
                [{"event": "DockingGranted", "LandingPad": 40}],
                [{"event": "Docked", "StationName": "Pawelczyk Dock"}],
            ]
        )
        time_values = iter([0.0, 0.0, 0.0, 0.1, 0.1, 0.2])
        sleep_calls: list[float] = []

        result = dock(
            controls,
            watcher,
            wait_for_supercruise_exit=True,
            auto_refuel=False,
            max_retries=1,
            request_timeout_s=10.0,
            dock_timeout_s=60.0,
            time_fn=lambda: next(time_values),
            sleeper=sleep_calls.append,
        )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(result.trigger_event, {"event": "Docked", "StationName": "Pawelczyk Dock"})
        self.assertEqual(result.details["request_event"], {"event": "DockingGranted", "LandingPad": 40})
        self.assertEqual(result.details["supercruise_exit_event"], {"event": "SupercruiseExit", "BodyType": "Station"})
        self.assertEqual(controls.calls[0], {"action": "BoostButton", "repeat": 1, "hold_s": 0.0})
        self.assertEqual(controls.calls[-1], {"action": "SetSpeedZero", "repeat": 2, "hold_s": 0.0})
        self.assertEqual(sleep_calls, [3.0, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 1.0])

    def test_dock_retries_after_docking_denied(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=ActionDispatchResult(
                action="SetSpeedZero",
                status="ok",
                binding=NormalizedBinding(key="x", modifier=None),
            )
        )
        watcher = FakeWatcher(
            [
                [],  # absorbed by prime poll() (wait_for_supercruise_exit=False)
                [{"event": "DockingDenied", "Reason": "TooLarge", "StationName": "Big Station"}],
                [{"event": "DockingGranted", "LandingPad": 1, "StationName": "Big Station"}],
                [{"event": "Docked", "StationName": "Big Station"}],
            ]
        )
        time_values = iter([0.0, 0.1, 0.1, 0.2, 0.2, 0.3])
        sleep_calls: list[float] = []

        result = dock(
            controls,
            watcher,
            wait_for_supercruise_exit=False,
            auto_refuel=False,
            max_retries=2,
            request_timeout_s=10.0,
            dock_timeout_s=60.0,
            deny_retry_delay_s=5.0,
            time_fn=lambda: next(time_values),
            sleeper=sleep_calls.append,
        )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(result.trigger_event, {"event": "Docked", "StationName": "Big Station"})
        self.assertIn(5.0, sleep_calls)

    def test_dock_can_skip_supercruise_exit_and_chain_refuel(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=ActionDispatchResult(
                action="UI_Down",
                status="ok",
                binding=NormalizedBinding(key="down", modifier=None),
            )
        )
        watcher = FakeWatcher(
            [
                [],  # absorbed by prime poll() before the retry loop
                [{"event": "DockingRequested"}],
                [{"event": "Docked", "StationName": "Pawelczyk Dock"}],
            ]
        )
        time_values = iter([0.0, 0.0, 0.1, 0.1])
        sleep_calls: list[float] = []

        result = dock(
            controls,
            watcher,
            wait_for_supercruise_exit=False,
            auto_refuel=True,
            max_retries=1,
            request_timeout_s=10.0,
            dock_timeout_s=60.0,
            settle_s=2.0,
            time_fn=lambda: next(time_values),
            sleeper=sleep_calls.append,
        )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(result.details["auto_refuel"], True)
        self.assertEqual(result.details["followup_action"], "station_refuel_menu")
        self.assertEqual(result.details["supercruise_exit_event"], None)
        self.assertEqual(sleep_calls, [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 1.0, 2.0, 0.5, 0.5])
        self.assertEqual(
            controls.calls[-3:],
            [
                {"action": "UI_Up", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Select", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Down", "repeat": 1, "hold_s": 0.0},
            ],
        )


_OK = ActionDispatchResult(action="ok", status="ok", binding=NormalizedBinding(key="x", modifier=None))


def _make_gal_map_controls() -> FakeShipControls:
    return FakeShipControls(set_speed_zero_result=_OK)


def _write_navroute(journal_dir: Path, system: str) -> None:
    navroute = {"Route": [{"StarSystem": "Sol"}, {"StarSystem": system}]}
    (journal_dir / "NavRoute.json").write_text(json.dumps(navroute), encoding="utf-8")


class GalMapDestinationTests(unittest.TestCase):
    def _run(
        self,
        controls: FakeShipControls,
        destination: str,
        journal_dir: Path,
    ) -> RoutineResult:
        return set_gal_map_destination(
            controls,
            destination=destination,
            journal_dir=journal_dir,
            open_settle_s=0.0,
            search_settle_s=0.0,
            plot_settle_s=0.0,
            step_delay_s=0.0,
            sleeper=lambda _: None,
        )

    def test_happy_path_plots_and_closes(self) -> None:
        controls = _make_gal_map_controls()
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_dir = Path(tmpdir)
            _write_navroute(journal_dir, "Colonia")

            result = self._run(controls, "Colonia", journal_dir)

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(result.details["destination"], "Colonia")
        self.assertEqual(result.details["actual"], "Colonia")

        actions = [c["action"] for c in controls.calls]
        self.assertEqual(actions[0], "GalaxyMapOpen")
        self.assertIn("UI_Up", actions)
        self.assertNotIn("CamZoomIn", actions)
        self.assertEqual(actions[-1], "GalaxyMapOpen")

    def test_types_destination_then_enter(self) -> None:
        controls = _make_gal_map_controls()
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_dir = Path(tmpdir)
            _write_navroute(journal_dir, "Sagittarius A*")

            self._run(controls, "Sagittarius A*", journal_dir)

        text_calls = [c for c in controls.calls if c["action"] == "type_text"]
        texts = [c["text"] for c in text_calls]
        self.assertIn("Sagittarius A*", texts)
        self.assertIn("\n", texts)

    def test_select_sequence_is_ui_right_then_held_select(self) -> None:
        controls = _make_gal_map_controls()
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_dir = Path(tmpdir)
            _write_navroute(journal_dir, "Sol")

            self._run(controls, "Sol", journal_dir)

        actions = [c["action"] for c in controls.calls]
        right_idx = actions.index("UI_Right")
        # UI_Select with hold immediately follows UI_Right
        self.assertEqual(actions[right_idx + 1], "UI_Select")
        select_call = controls.calls[right_idx + 1]
        self.assertGreater(select_call["hold_s"], 0)

    def test_mismatch_returns_error_and_closes_map(self) -> None:
        controls = _make_gal_map_controls()
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_dir = Path(tmpdir)
            _write_navroute(journal_dir, "Wrong System")

            result = self._run(controls, "Target", journal_dir)

        self.assertEqual(result.dispatch.status, "error")
        actions = [c["action"] for c in controls.calls]
        self.assertEqual(actions[-1], "GalaxyMapOpen")
        self.assertNotIn("UI_Down", actions)

    def test_missing_navroute_returns_error(self) -> None:
        controls = _make_gal_map_controls()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run(controls, "Sol", Path(tmpdir))

        self.assertEqual(result.dispatch.status, "error")

    def test_case_insensitive_match(self) -> None:
        controls = _make_gal_map_controls()
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_dir = Path(tmpdir)
            _write_navroute(journal_dir, "COLONIA")

            result = self._run(controls, "colonia", journal_dir)

        self.assertEqual(result.dispatch.status, "ok")

    def test_open_check_fn_polled_until_true(self) -> None:
        controls = _make_gal_map_controls()
        call_count = 0

        def check_fn() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 3

        with tempfile.TemporaryDirectory() as tmpdir:
            journal_dir = Path(tmpdir)
            _write_navroute(journal_dir, "Sol")
            t = [0.0]

            set_gal_map_destination(
                controls,
                destination="Sol",
                journal_dir=journal_dir,
                open_check_fn=check_fn,
                open_timeout_s=100.0,
                step_delay_s=0.0,
                search_settle_s=0.0,
                plot_settle_s=0.0,
                sleeper=lambda _: None,
                time_fn=lambda: t[0],
            )

        self.assertGreaterEqual(call_count, 3)
