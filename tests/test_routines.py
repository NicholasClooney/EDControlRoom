from __future__ import annotations

import unittest

from edap.actions import ActionDispatchResult
from edap.binding_lookup import NormalizedBinding
from edap.routines import (
    RoutineResult,
    auto_zero_throttle_on_arrival,
    dock,
    docking_request_sequence,
    jump,
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

    def ui_right(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"action": "UI_Right", "repeat": repeat, "hold_s": hold_s})
        return self._set_speed_zero_result


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
                {"action": "CyclePreviousPanel", "repeat": 1, "hold_s": 0.0},
                {"action": "CyclePreviousPanel", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Back", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertEqual(sleep_calls, [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 1.0])

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
        self.assertEqual(controls.calls[-1], {"action": "SetSpeedZero", "repeat": 2, "hold_s": 0.0})
        self.assertEqual(sleep_calls, [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 1.0])

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
        self.assertEqual(sleep_calls, [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 1.0, 2.0, 0.5, 0.5])
        self.assertEqual(
            controls.calls[-3:],
            [
                {"action": "UI_Up", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Select", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Down", "repeat": 1, "hold_s": 0.0},
            ],
        )
