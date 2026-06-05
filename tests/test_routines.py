from __future__ import annotations

import unittest

from edap.actions import ActionDispatchResult
from edap.binding_lookup import NormalizedBinding
from edap.routines import RoutineResult, auto_zero_throttle_on_arrival, set_speed_zero_then_wait


class FakeShipControls:
    def __init__(self, result: ActionDispatchResult) -> None:
        self.calls: list[dict[str, object]] = []
        self._result = result

    def set_speed_zero(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        self.calls.append({"repeat": repeat, "hold_s": hold_s})
        return self._result


class RoutinesTests(unittest.TestCase):
    def test_set_speed_zero_then_wait_dispatches_and_sleeps(self) -> None:
        controls = FakeShipControls(
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
        self.assertEqual(controls.calls, [{"repeat": 2, "hold_s": 0.05}])
        self.assertEqual(sleep_calls, [1.25])

    def test_set_speed_zero_then_wait_skips_sleep_when_wait_is_zero(self) -> None:
        controls = FakeShipControls(
            ActionDispatchResult(
                action="SetSpeedZero",
                status="ok",
                binding=NormalizedBinding(key="x", modifier=None),
            )
        )
        sleep_calls: list[float] = []

        result = set_speed_zero_then_wait(controls, sleeper=sleep_calls.append)

        self.assertEqual(result.wait_s, 0.0)
        self.assertEqual(controls.calls, [{"repeat": 1, "hold_s": 0.0}])
        self.assertEqual(sleep_calls, [])

    def test_set_speed_zero_then_wait_skips_sleep_when_dispatch_fails(self) -> None:
        controls = FakeShipControls(
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

        self.assertEqual(controls.calls, [{"repeat": 2, "hold_s": 0.05}])
        self.assertEqual(result.action, "SetSpeedZero")
        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(result.trigger_event, {"event": "SupercruiseExit", "StarSystem": "Achenar"})

    def test_auto_zero_throttle_on_arrival_raises_if_stream_ends_without_event(self) -> None:
        controls = FakeShipControls(
            ActionDispatchResult(
                action="SetSpeedZero",
                status="ok",
                binding=NormalizedBinding(key="x", modifier=None),
            )
        )

        with self.assertRaisesRegex(RuntimeError, "SupercruiseExit"):
            auto_zero_throttle_on_arrival(controls, [{"event": "LoadGame"}])

        self.assertEqual(controls.calls, [])
