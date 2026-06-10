from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from edap.actions import ActionDispatchResult
from edap.binding_lookup import NormalizedBinding
from edap.routines import (
    RoutineResult,
    auto_zero_throttle_on_arrival as _auto_zero_throttle_on_arrival,
    dock as _dock,
    docking_request_sequence,
    escape_mass_lock as _escape_mass_lock,
    jump as _jump,
    market_buy as _market_buy,
    market_sell as _market_sell,
    set_gal_map_destination as _set_gal_map_destination,
    set_speed_zero_then_wait,
    station_refuel_menu as _station_refuel_menu,
    station_refuel_menu_sequence,
    undock as _undock,
)
from edap.routines._callbacks import noop_announce, noop_progress
from edap.tts import AnnouncementId
from tests.fakes import FakeShipControls, FakeWatcher


def auto_zero_throttle_on_arrival(*args, **kwargs):
    kwargs.setdefault("progress_fn", noop_progress)
    return _auto_zero_throttle_on_arrival(*args, **kwargs)


def jump(*args, **kwargs):
    kwargs.setdefault("progress_fn", noop_progress)
    return _jump(*args, **kwargs)


def station_refuel_menu(*args, **kwargs):
    kwargs.setdefault("progress_fn", noop_progress)
    return _station_refuel_menu(*args, **kwargs)


def dock(*args, **kwargs):
    kwargs.setdefault("progress_fn", noop_progress)
    kwargs.setdefault("announce_fn", noop_announce)
    return _dock(*args, **kwargs)


def undock(*args, **kwargs):
    kwargs.setdefault("progress_fn", noop_progress)
    return _undock(*args, **kwargs)


def market_buy(*args, **kwargs):
    kwargs.setdefault("progress_fn", noop_progress)
    kwargs.setdefault("announce_fn", noop_announce)
    return _market_buy(*args, **kwargs)


def market_sell(*args, **kwargs):
    kwargs.setdefault("progress_fn", noop_progress)
    kwargs.setdefault("announce_fn", noop_announce)
    return _market_sell(*args, **kwargs)


def escape_mass_lock(*args, **kwargs):
    kwargs.setdefault("progress_fn", noop_progress)
    return _escape_mass_lock(*args, **kwargs)


def set_gal_map_destination(*args, **kwargs):
    kwargs.setdefault("progress_fn", noop_progress)
    return _set_gal_map_destination(*args, **kwargs)


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

    def test_station_refuel_menu_sequence_dispatches_refuel_repair_then_down(self) -> None:
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
                {"action": "UI_Right", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Select", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Down", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertEqual(sleep_calls, [0.5, 0.5, 0.5, 0.5])
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
                {"action": "UI_Right", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Select", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Down", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertEqual(sleep_calls, [2.0, 0.5, 0.5, 0.5, 0.5])

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

    def test_undock_waits_for_no_track_after_undocked(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([
            [],
            [{"event": "Undocked", "StationName": "Pawelczyk Dock"}],
            [{"event": "Music", "MusicTrack": "DockingComputer"}],
            [{"event": "Music", "MusicTrack": "NoTrack"}],
        ])
        time_values = iter([0.0, 0.0, 0.1, 0.2, 0.3, 0.4])

        result = undock(
            controls,
            watcher,
            undock_timeout_s=1.0,
            no_track_timeout_s=1.0,
            step_delay_s=0.0,
            time_fn=lambda: next(time_values),
            sleeper=lambda _: None,
        )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(result.action, "NoTrack")
        self.assertEqual(result.trigger_event, {"event": "Music", "MusicTrack": "NoTrack"})
        self.assertEqual(result.details["undocked_event"], {"event": "Undocked", "StationName": "Pawelczyk Dock"})

    def test_undock_preserves_same_batch_no_track_after_undocked(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([
            [],
            [
                {"event": "Undocked", "StationName": "Pawelczyk Dock"},
                {"event": "Music", "MusicTrack": "NoTrack"},
            ],
        ])
        time_values = iter([0.0, 0.0, 0.1, 0.2])

        result = undock(
            controls,
            watcher,
            undock_timeout_s=1.0,
            no_track_timeout_s=1.0,
            step_delay_s=0.0,
            time_fn=lambda: next(time_values),
            sleeper=lambda _: None,
        )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(result.action, "NoTrack")
        self.assertEqual(result.trigger_event, {"event": "Music", "MusicTrack": "NoTrack"})

    def test_undock_errors_if_no_track_never_arrives(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([
            [],
            [{"event": "Undocked", "StationName": "Pawelczyk Dock"}],
            [{"event": "Music", "MusicTrack": "DockingComputer"}],
        ])
        time_values = iter([0.0, 0.0, 0.1, 0.2, 0.3, 1.2])

        result = undock(
            controls,
            watcher,
            undock_timeout_s=1.0,
            no_track_timeout_s=1.0,
            step_delay_s=0.0,
            time_fn=lambda: next(time_values),
            sleeper=lambda _: None,
        )

        self.assertEqual(result.dispatch.status, "error")
        self.assertIn("NoTrack", result.dispatch.reason)

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
                {"action": "UI_Left", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Left", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Left", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Right", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Select", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Left", "repeat": 1, "hold_s": 0.0},
                {"action": "CyclePreviousPanel", "repeat": 1, "hold_s": 0.0},
                {"action": "CyclePreviousPanel", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Back", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertEqual(sleep_calls, [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 1.0])

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
        self.assertEqual(controls.calls[0], {"action": "UseBoostJuice", "repeat": 1, "hold_s": 0.0})
        self.assertEqual(controls.calls[-1], {"action": "SetSpeedZero", "repeat": 2, "hold_s": 0.0})
        self.assertEqual(
            sleep_calls,
            [3.0, 3.0, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 1.0],
        )

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

    def test_dock_announces_request_once_before_retries(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=ActionDispatchResult(
                action="SetSpeedZero",
                status="ok",
                binding=NormalizedBinding(key="x", modifier=None),
            )
        )
        watcher = FakeWatcher(
            [
                [],
                [{"event": "DockingDenied", "Reason": "TooLarge", "StationName": "Big Station"}],
                [{"event": "DockingGranted", "LandingPad": 1, "StationName": "Big Station"}],
                [{"event": "Docked", "StationName": "Big Station"}],
            ]
        )
        time_values = iter([0.0, 0.1, 0.1, 0.2, 0.2, 0.3])
        announcements: list[tuple[object, dict[str, object]]] = []

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
            sleeper=lambda _: None,
            announce_fn=lambda message_id, **values: announcements.append((message_id, values)),
            announce_station_name="Big Station",
        )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(
            announcements,
            [
                (AnnouncementId.DOCKING_REQUEST, {"station_name": "Big Station"}),
                (AnnouncementId.AUTO_DOCKING_ENGAGED, {}),
            ],
        )

    def test_dock_announces_auto_docking_when_granted(self) -> None:
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
                [],
                [{"event": "DockingGranted", "LandingPad": 40}],
                [{"event": "Docked", "StationName": "Pawelczyk Dock"}],
            ]
        )
        time_values = iter([0.0, 0.0, 0.0, 0.1, 0.1, 0.2])
        announcements: list[tuple[object, dict[str, object]]] = []

        result = dock(
            controls,
            watcher,
            wait_for_supercruise_exit=True,
            auto_refuel=False,
            max_retries=1,
            request_timeout_s=10.0,
            dock_timeout_s=60.0,
            time_fn=lambda: next(time_values),
            sleeper=lambda _: None,
            announce_fn=lambda message_id, **values: announcements.append((message_id, values)),
        )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(
            announcements,
            [(AnnouncementId.AUTO_DOCKING_ENGAGED, {})],
        )

    def test_dock_can_skip_supercruise_exit_and_chain_refuel_and_repair(self) -> None:
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
        announcements: list[tuple[AnnouncementId, dict[str, object]]] = []

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
            announce_fn=lambda message_id, **values: announcements.append((message_id, values)),
        )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(result.details["auto_refuel"], True)
        self.assertEqual(result.details["followup_action"], "station_refuel_menu")
        self.assertEqual(result.details["supercruise_exit_event"], None)
        self.assertEqual(sleep_calls, [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 1.0, 2.0, 0.5, 0.5, 0.5, 0.5])
        self.assertEqual(
            controls.calls[-5:],
            [
                {"action": "UI_Up", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Select", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Right", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Select", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Down", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertEqual(
            announcements,
            [
                (AnnouncementId.AUTO_DOCKING_ENGAGED, {}),
                (AnnouncementId.SHIP_SERVICED, {}),
            ],
        )

    def test_market_sell_spaces_back_presses_after_trade(self) -> None:
        controls = FakeShipControls(
            set_speed_zero_result=ActionDispatchResult(
                action="UI_Select",
                status="ok",
                binding=NormalizedBinding(key="space", modifier=None),
            )
        )
        watcher = FakeWatcher(
            [[{"event": "MarketSell", "Type": "aluminium", "Type_Localised": "aluminium", "Count": 461, "TotalSale": 9367520}]]
        )
        sleep_calls: list[float] = []

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                json.dumps({"timestamp": "2024-01-01T00:00:00Z", "event": "Docked", "StationName": "Pawelczyk Dock"}) + "\n",
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {"Category": "Metals", "Name": "aluminium", "DemandBracket": 1},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_sell(
                controls,
                watcher,
                market_path=market_path,
                target="aluminium",
                amount="MAX",
                step_delay_s=0.5,
                trade_timeout_s=30.0,
                skip_station_check=True,
                time_fn=lambda: 0.0,
                sleeper=sleep_calls.append,
            )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(
            controls.calls[:4],
            [
                {"action": "UI_Back", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Back", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Back", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Back", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertEqual(
            controls.calls[-4:],
            [
                {"action": "UI_Back", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Back", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Back", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Back", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertGreaterEqual(sleep_calls.count(0.5), 9)

    def test_market_buy_resets_trade_dialog_focus_before_setting_quantity(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher(
            [[{"event": "MarketBuy", "Type": "aluminium", "Type_Localised": "Aluminium", "Count": 1, "TotalCost": 1234}]]
        )

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                json.dumps({
                    "timestamp": "2024-01-01T00:00:00Z",
                    "event": "Location",
                    "Docked": True,
                    "StationName": "Pawelczyk Dock",
                }) + "\n",
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {"Category": "Metals", "Name": "aluminium", "Stock": 1000},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_buy(
                controls,
                watcher,
                market_path=market_path,
                target="aluminium",
                amount=1,
                step_delay_s=0.0,
                nav_delay_s=0.0,
                trade_timeout_s=30.0,
                time_fn=lambda: 0.0,
                sleeper=lambda _: None,
            )

        self.assertEqual(result.dispatch.status, "ok")
        dialog_index = controls.calls.index({"action": "UI_Select", "repeat": 1, "hold_s": 0.0}, 7)
        self.assertEqual(
            controls.calls[dialog_index + 1:dialog_index + 7],
            [
                {"action": "UI_Left", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Left", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Left", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Up", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Up", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Up", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertEqual(
            controls.calls[dialog_index + 7:dialog_index + 9],
            [
                {"action": "UI_Right", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Down", "repeat": 1, "hold_s": 0.0},
            ],
        )

    def test_market_sell_requires_current_docked_state(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([])

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                json.dumps({"timestamp": "2024-01-01T00:00:00Z", "event": "Undocked", "StarSystem": "HIP 58412"}) + "\n",
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {"Category": "Metals", "Name": "aluminium", "DemandBracket": 1, "SellPrice": 1000},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_sell(
                controls,
                watcher,
                market_path=market_path,
                target="aluminium",
                amount="MAX",
                step_delay_s=0.0,
                trade_timeout_s=30.0,
                skip_station_check=True,
                time_fn=lambda: 0.0,
                sleeper=lambda _: None,
            )

        self.assertEqual(result.dispatch.status, "error")
        self.assertIn("sell requires an in-station start", result.dispatch.reason or "")

    def test_market_sell_rechecks_current_docked_state_after_backing_out(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher(
            [
                [],
                [{"event": "MarketSell", "Type": "aluminium", "Type_Localised": "Aluminium", "Count": 10, "TotalSale": 1234}],
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            journal_path = journal_dir / "Journal.240101000000.01.log"
            journal_path.write_text(
                json.dumps({"timestamp": "2024-01-01T00:00:00Z", "event": "Docked", "StationName": "Pawelczyk Dock"}) + "\n",
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {"Category": "Metals", "Name": "aluminium", "DemandBracket": 1, "SellPrice": 1000},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            def sleeper(_: float) -> None:
                if "Undocked" not in journal_path.read_text(encoding="utf-8"):
                    journal_path.write_text(
                        "\n".join([
                            json.dumps({"timestamp": "2024-01-01T00:00:00Z", "event": "Docked", "StationName": "Pawelczyk Dock"}),
                            json.dumps({"timestamp": "2024-01-01T00:00:01Z", "event": "Undocked", "StarSystem": "HIP 58412"}),
                        ]) + "\n",
                        encoding="utf-8",
                    )

            result = market_sell(
                controls,
                watcher,
                market_path=market_path,
                target="aluminium",
                amount="MAX",
                step_delay_s=0.0,
                trade_timeout_s=30.0,
                skip_station_check=True,
                time_fn=lambda: 0.0,
                sleeper=sleeper,
            )

        self.assertEqual(result.dispatch.status, "error")
        self.assertIn("sell return-to-station check failed", result.dispatch.reason or "")

    def test_market_buy_accepts_location_docked_true_for_station_check(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher(
            [[{"event": "MarketBuy", "Type": "aluminium", "Type_Localised": "Aluminium", "Count": 1, "TotalCost": 1234}]]
        )
        progress: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                "\n".join([
                    json.dumps({
                        "timestamp": "2024-01-01T00:00:00Z",
                        "event": "Location",
                        "Docked": True,
                        "StationName": "Pawelczyk Dock",
                        "StarSystem": "HIP 58412",
                    }),
                    json.dumps({
                        "timestamp": "2024-01-01T00:00:01Z",
                        "event": "Loadout",
                        "CargoCapacity": 64,
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {"Category": "Metals", "Name": "aluminium", "Stock": 1000},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_buy(
                controls,
                watcher,
                market_path=market_path,
                target="aluminium",
                amount=1,
                step_delay_s=0.0,
                nav_delay_s=0.0,
                trade_timeout_s=30.0,
                time_fn=lambda: 0.0,
                sleeper=lambda _: None,
                progress_fn=progress.append,
            )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertIn(
            "Station supply for aluminium looks normal at 1000 units (critical below 640).",
            progress,
        )

    def test_market_buy_max_scales_hold_time_from_available_cargo_space(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher(
            [[{"event": "MarketBuy", "Type": "aluminium", "Type_Localised": "Aluminium", "Count": 46, "TotalCost": 1234}]]
        )
        progress: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                "\n".join([
                    json.dumps({
                        "timestamp": "2024-01-01T00:00:00Z",
                        "event": "Location",
                        "Docked": True,
                        "StationName": "Pawelczyk Dock",
                    }),
                    json.dumps({
                        "timestamp": "2024-01-01T00:00:01Z",
                        "event": "Loadout",
                        "CargoCapacity": 512,
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            (journal_dir / "Cargo.json").write_text(
                json.dumps(
                    {
                        "Inventory": [
                            {"Name": "gold", "Count": 52},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {"Category": "Metals", "Name": "aluminium", "Stock": 1000},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_buy(
                controls,
                watcher,
                market_path=market_path,
                target="aluminium",
                amount="MAX",
                step_delay_s=0.0,
                nav_delay_s=0.0,
                buy_hold_seconds_per_ton=0.01,
                trade_timeout_s=30.0,
                time_fn=lambda: 0.0,
                sleeper=lambda _: None,
                progress_fn=progress.append,
            )

        self.assertEqual(result.dispatch.status, "ok")
        hold_calls = [call for call in controls.calls if call["action"] == "UI_Right" and call["hold_s"]]
        self.assertEqual(len(hold_calls), 1)
        self.assertAlmostEqual(float(hold_calls[0]["hold_s"]), 4.6)
        self.assertIn(
            "  UI_Right hold 4.60s (fill to max from min(460t free, 1000t supply) at 0.0100s/t)",
            progress,
        )

    def test_market_buy_max_clamps_hold_time_to_station_supply(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher(
            [[{"event": "MarketBuy", "Type": "aluminium", "Type_Localised": "Aluminium", "Count": 120, "TotalCost": 1234}]]
        )
        progress: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                "\n".join([
                    json.dumps({
                        "timestamp": "2024-01-01T00:00:00Z",
                        "event": "Location",
                        "Docked": True,
                        "StationName": "Pawelczyk Dock",
                    }),
                    json.dumps({
                        "timestamp": "2024-01-01T00:00:01Z",
                        "event": "Loadout",
                        "CargoCapacity": 512,
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            (journal_dir / "Cargo.json").write_text(
                json.dumps(
                    {
                        "Inventory": [
                            {"Name": "gold", "Count": 12},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {"Category": "Metals", "Name": "aluminium", "Stock": 120},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_buy(
                controls,
                watcher,
                market_path=market_path,
                target="aluminium",
                amount="MAX",
                step_delay_s=0.0,
                nav_delay_s=0.0,
                buy_hold_seconds_per_ton=0.01,
                trade_timeout_s=30.0,
                time_fn=lambda: 0.0,
                sleeper=lambda _: None,
                progress_fn=progress.append,
            )

        self.assertEqual(result.dispatch.status, "ok")
        hold_calls = [call for call in controls.calls if call["action"] == "UI_Right" and call["hold_s"]]
        self.assertEqual(len(hold_calls), 1)
        self.assertAlmostEqual(float(hold_calls[0]["hold_s"]), 1.2)
        self.assertIn(
            "  UI_Right hold 1.20s (fill to max from min(500t free, 120t supply) at 0.0100s/t)",
            progress,
        )

    def test_market_buy_max_falls_back_to_cap_when_available_cargo_space_is_unknown(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher(
            [[{"event": "MarketBuy", "Type": "aluminium", "Type_Localised": "Aluminium", "Count": 46, "TotalCost": 1234}]]
        )
        progress: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                json.dumps({
                    "timestamp": "2024-01-01T00:00:01Z",
                    "event": "Loadout",
                    "CargoCapacity": 512,
                }) + "\n",
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {"Category": "Metals", "Name": "aluminium", "Stock": 1000},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_buy(
                controls,
                watcher,
                market_path=market_path,
                target="aluminium",
                amount="MAX",
                step_delay_s=0.0,
                nav_delay_s=0.0,
                max_hold_s=10.0,
                buy_hold_seconds_per_ton=0.01,
                trade_timeout_s=30.0,
                skip_station_check=True,
                time_fn=lambda: 0.0,
                sleeper=lambda _: None,
                progress_fn=progress.append,
            )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertIn({"action": "UI_Right", "repeat": 1, "hold_s": 10.0}, controls.calls)
        self.assertIn(
            "  UI_Right hold 10.00s (fill to max from 1000t supply at 0.0100s/t)",
            progress,
        )

    def test_market_buy_rejects_when_no_docked_station_state_exists(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher([])

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                json.dumps({
                    "timestamp": "2024-01-01T00:00:00Z",
                    "event": "SupercruiseEntry",
                    "StarSystem": "HIP 58412",
                }) + "\n",
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {"Category": "Metals", "Name": "aluminium", "Stock": 10},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_buy(
                controls,
                watcher,
                market_path=market_path,
                target="aluminium",
                amount=1,
                step_delay_s=0.0,
                nav_delay_s=0.0,
                trade_timeout_s=30.0,
                time_fn=lambda: 0.0,
                sleeper=lambda _: None,
            )

        self.assertEqual(result.dispatch.status, "error")
        self.assertIn("no docked station state found", result.dispatch.reason or "")

    def test_market_sell_warns_and_announces_when_demand_is_low(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher(
            [[{"event": "MarketSell", "Type": "aluminium", "Type_Localised": "Aluminium", "Count": 64, "TotalSale": 9367520}]]
        )
        progress: list[str] = []
        announcements: list[tuple[AnnouncementId, dict[str, object]]] = []

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                "\n".join([
                    json.dumps({
                        "timestamp": "2024-01-01T00:00:00Z",
                        "event": "Docked",
                        "StationName": "Pawelczyk Dock",
                    }),
                    json.dumps({
                        "timestamp": "2024-01-01T00:00:01Z",
                        "event": "Loadout",
                        "CargoCapacity": 64,
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {
                                "Category": "Metals",
                                "Name": "aluminium",
                                "Name_Localised": "Aluminium",
                                "Demand": 200,
                                "DemandBracket": 1,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_sell(
                controls,
                watcher,
                market_path=market_path,
                target="aluminium",
                amount="MAX",
                step_delay_s=0.0,
                nav_delay_s=0.0,
                trade_timeout_s=30.0,
                skip_station_check=True,
                time_fn=lambda: 0.0,
                sleeper=lambda _: None,
                progress_fn=progress.append,
                announce_fn=lambda message_id, **values: announcements.append((message_id, values)),
            )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertIn(
            "Warning: Station demand for Aluminium is low at 200 units (critical below 640).",
            progress,
        )
        self.assertEqual(
            announcements,
            [
                (
                    AnnouncementId.MARKET_LEVEL_LOW,
                    {"market_side": "demand", "commodity_name": "Aluminium", "units": 200},
                )
            ],
        )

    def test_market_sell_allows_zero_demand_when_sell_price_is_present(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher(
            [[{"event": "MarketSell", "Type": "foodcartridges", "Type_Localised": "Food Cartridges", "Count": 64, "TotalSale": 123456}]]
        )
        progress: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                json.dumps({"timestamp": "2024-01-01T00:00:00Z", "event": "Docked", "StationName": "Pawelczyk Dock"}) + "\n",
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {
                                "Category": "Foods",
                                "Name": "foodcartridges",
                                "Name_Localised": "Food Cartridges",
                                "Demand": 0,
                                "DemandBracket": 0,
                                "SellPrice": 1929,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_sell(
                controls,
                watcher,
                market_path=market_path,
                target="Food Cartridges",
                amount="MAX",
                step_delay_s=0.0,
                nav_delay_s=0.0,
                trade_timeout_s=30.0,
                skip_station_check=True,
                time_fn=lambda: 0.0,
                sleeper=lambda _: None,
                progress_fn=progress.append,
            )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertIn("Target 'Food Cartridges' at position 0 in sell list (1 items)", progress)
        self.assertIn(
            "Station demand for Food Cartridges is 0 units; cargo capacity unavailable, skipping low-level threshold check.",
            progress,
        )

    def test_market_sell_inserts_hidden_sellable_target_into_original_sell_order(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher(
            [[{"event": "MarketSell", "Type": "foodcartridges", "Type_Localised": "Food Cartridges", "Count": 64, "TotalSale": 123456}]]
        )
        progress: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                json.dumps({"timestamp": "2024-01-01T00:00:00Z", "event": "Docked", "StationName": "Pawelczyk Dock"}) + "\n",
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {
                                "Category": "Foods",
                                "Name": "algae",
                                "Name_Localised": "Algae",
                                "Demand": 557_928,
                                "DemandBracket": 1,
                                "SellPrice": 656,
                            },
                            {
                                "Category": "Foods",
                                "Name": "animalmeat",
                                "Name_Localised": "Animal Meat",
                                "Demand": 26_603,
                                "DemandBracket": 1,
                                "SellPrice": 1927,
                            },
                            {
                                "Category": "Foods",
                                "Name": "coffee",
                                "Name_Localised": "Coffee",
                                "Demand": 7_577,
                                "DemandBracket": 1,
                                "SellPrice": 1926,
                            },
                            {
                                "Category": "Foods",
                                "Name": "fish",
                                "Name_Localised": "Fish",
                                "Demand": 76_275,
                                "DemandBracket": 1,
                                "SellPrice": 942,
                            },
                            {
                                "Category": "Foods",
                                "Name": "foodcartridges",
                                "Name_Localised": "Food Cartridges",
                                "Demand": 0,
                                "DemandBracket": 0,
                                "SellPrice": 1929,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_sell(
                controls,
                watcher,
                market_path=market_path,
                target="Food Cartridges",
                amount="MAX",
                step_delay_s=0.0,
                nav_delay_s=0.0,
                trade_timeout_s=30.0,
                skip_station_check=True,
                time_fn=lambda: 0.0,
                sleeper=lambda _: None,
                progress_fn=progress.append,
            )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertIn("Target 'Food Cartridges' at position 4 in sell list (5 items)", progress)
        self.assertIn("  UI_Down x4 (navigate to 'Food Cartridges')", progress)

    def test_market_sell_resets_trade_dialog_focus_before_confirm(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher(
            [[{"event": "MarketSell", "Type": "aluminium", "Type_Localised": "Aluminium", "Count": 64, "TotalSale": 123456}]]
        )

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                json.dumps({"timestamp": "2024-01-01T00:00:00Z", "event": "Docked", "StationName": "Pawelczyk Dock"}) + "\n",
                encoding="utf-8",
            )
            (journal_dir / "Cargo.json").write_text(
                json.dumps(
                    {
                        "Inventory": [
                            {"Name": "aluminium", "Name_Localised": "Aluminium", "Count": 64},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {"Category": "Metals", "Name": "aluminium", "DemandBracket": 1, "SellPrice": 1000},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_sell(
                controls,
                watcher,
                market_path=market_path,
                target="aluminium",
                amount="MAX",
                step_delay_s=0.0,
                nav_delay_s=0.0,
                trade_timeout_s=30.0,
                skip_station_check=True,
                time_fn=lambda: 0.0,
                sleeper=lambda _: None,
            )

        self.assertEqual(result.dispatch.status, "ok")
        dialog_index = controls.calls.index({"action": "UI_Select", "repeat": 1, "hold_s": 0.0}, 9)
        self.assertEqual(
            controls.calls[dialog_index + 1:dialog_index + 7],
            [
                {"action": "UI_Left", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Left", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Left", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Up", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Up", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Up", "repeat": 1, "hold_s": 0.0},
            ],
        )
        self.assertEqual(
            controls.calls[dialog_index + 7:dialog_index + 10],
            [
                {"action": "UI_Right", "repeat": 1, "hold_s": 0.64},
                {"action": "UI_Down", "repeat": 1, "hold_s": 0.0},
                {"action": "UI_Select", "repeat": 1, "hold_s": 0.0},
            ],
        )

    def test_market_sell_max_restores_quantity_with_hold_after_focus_reset(self) -> None:
        controls = FakeShipControls()
        watcher = FakeWatcher(
            [[{"event": "MarketSell", "Type": "aluminium", "Type_Localised": "Aluminium", "Count": 32, "TotalSale": 654321}]]
        )
        progress: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            (journal_dir / "Journal.240101000000.01.log").write_text(
                json.dumps({"timestamp": "2024-01-01T00:00:00Z", "event": "Docked", "StationName": "Pawelczyk Dock"}) + "\n",
                encoding="utf-8",
            )
            (journal_dir / "Cargo.json").write_text(
                json.dumps(
                    {
                        "Inventory": [
                            {"Name": "aluminium", "Name_Localised": "Aluminium", "Count": 32},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            market_path = journal_dir / "Market.json"
            market_path.write_text(
                json.dumps(
                    {
                        "StationName": "Pawelczyk Dock",
                        "Items": [
                            {"Category": "Metals", "Name": "aluminium", "DemandBracket": 1, "SellPrice": 1000},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = market_sell(
                controls,
                watcher,
                market_path=market_path,
                target="aluminium",
                amount="MAX",
                step_delay_s=0.0,
                nav_delay_s=0.0,
                trade_timeout_s=30.0,
                skip_station_check=True,
                buy_hold_seconds_per_ton=0.01,
                time_fn=lambda: 0.0,
                sleeper=lambda _: None,
                progress_fn=progress.append,
            )

        self.assertEqual(result.dispatch.status, "ok")
        self.assertIn(
            "  UI_Right hold 0.32s (restore sell quantity to 32t at 0.0100s/t)",
            progress,
        )
        self.assertIn({"action": "UI_Right", "repeat": 1, "hold_s": 0.32}, controls.calls)


class EscapeMassLockTests(unittest.TestCase):
    def _write_status(self, journal_dir: Path, *, mass_locked: bool) -> None:
        flags = (1 << 16) if mass_locked else 0
        data = {"timestamp": "2024-01-01T00:00:00Z", "event": "Status", "Flags": flags}
        (journal_dir / "Status.json").write_text(json.dumps(data), encoding="utf-8")

    def test_not_mass_locked_returns_immediately_with_no_boosts(self) -> None:
        controls = FakeShipControls()
        sleep_calls: list[float] = []

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            self._write_status(journal_dir, mass_locked=False)

            result = escape_mass_lock(
                controls,
                journal_dir=journal_dir,
                boost_delay_s=5.0,
                step_delay_s=0.3,
                sleeper=sleep_calls.append,
            )

        self.assertIsInstance(result, RoutineResult)
        self.assertEqual(result.action, "EscapeMassLock")
        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(result.details["boost_count"], 0)
        boost_calls = [c for c in controls.calls if c["action"] == "UseBoostJuice"]
        self.assertEqual(boost_calls, [])
        self.assertEqual(sleep_calls, [0.3])

    def test_boosts_until_mass_lock_clears(self) -> None:
        controls = FakeShipControls()
        boost_calls_seen: list[int] = []

        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp)
            self._write_status(journal_dir, mass_locked=True)

            def sleeper(s: float) -> None:
                if s == 5.0 and len(boost_calls_seen) == 0:
                    boost_calls_seen.append(1)
                    self._write_status(journal_dir, mass_locked=False)

            result = escape_mass_lock(
                controls,
                journal_dir=journal_dir,
                boost_delay_s=5.0,
                step_delay_s=0.0,
                sleeper=sleeper,
            )

        self.assertEqual(result.action, "EscapeMassLock")
        self.assertEqual(result.dispatch.status, "ok")
        self.assertEqual(result.details["boost_count"], 1)
        boost_dispatches = [c for c in controls.calls if c["action"] == "UseBoostJuice"]
        self.assertEqual(len(boost_dispatches), 1)

    def test_rejects_negative_boost_delay(self) -> None:
        controls = FakeShipControls()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "boost_delay_s"):
                escape_mass_lock(controls, journal_dir=Path(tmp), boost_delay_s=-1.0)

    def test_rejects_negative_step_delay(self) -> None:
        controls = FakeShipControls()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "step_delay_s"):
                escape_mass_lock(controls, journal_dir=Path(tmp), step_delay_s=-0.1)

    def test_missing_status_file_exits_immediately(self) -> None:
        controls = FakeShipControls()
        with tempfile.TemporaryDirectory() as tmp:
            result = escape_mass_lock(
                controls,
                journal_dir=Path(tmp),
                boost_delay_s=5.0,
                step_delay_s=0.0,
                sleeper=lambda _: None,
            )
        self.assertEqual(result.details["boost_count"], 0)
        boost_calls = [c for c in controls.calls if c["action"] == "UseBoostJuice"]
        self.assertEqual(boost_calls, [])


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
            map_settle_s=0.0,
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
        self.assertIn("CamZoomIn", actions)
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
        enter_calls = [c for c in controls.calls if c["action"] == "Enter"]
        self.assertEqual(len(enter_calls), 1)
        self.assertGreater(enter_calls[0]["hold_s"], 0)

    def test_select_sequence_matches_odyssey_flow(self) -> None:
        controls = _make_gal_map_controls()
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_dir = Path(tmpdir)
            _write_navroute(journal_dir, "Sol")

            self._run(controls, "Sol", journal_dir)

        actions = [c["action"] for c in controls.calls]
        right_idx = actions.index("UI_Right")
        self.assertEqual(actions[right_idx + 1], "UI_Select")
        self.assertEqual(actions[right_idx + 2], "CamZoomIn")
        # Held UI_Select immediately follows CamZoomIn
        self.assertEqual(actions[right_idx + 3], "UI_Select")
        select_call = controls.calls[right_idx + 3]
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
                map_settle_s=0.0,
                sleeper=lambda _: None,
                time_fn=lambda: t[0],
            )

        self.assertGreaterEqual(call_count, 3)
