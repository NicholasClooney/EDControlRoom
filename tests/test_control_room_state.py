from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from edap.control_room_state import (
    CommandHistoryEntry,
    ControlRoomState,
    load_control_room_state,
    save_control_room_state,
)


class ControlRoomStateTests(unittest.TestCase):
    def test_load_missing_file_returns_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state = load_control_room_state(Path(temp_dir) / "missing.json")

        self.assertEqual(state.default_haul, {})
        self.assertEqual(state.history, [])
        self.assertFalse(state.instant_mode)

    def test_save_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            original = ControlRoomState(
                default_haul={"station_1_buying": "Aluminium", "station_2": "Hutton Orbital"},
                instant_mode=True,
                history=[
                    CommandHistoryEntry(
                        raw="haul Aluminium",
                        command="haul",
                        params={"station_1_buying": "Aluminium", "dock_timeout": "600.0"},
                        timestamp="2026-06-07T12:00:00Z",
                    )
                ],
            )

            save_control_room_state(path, original)
            loaded = load_control_room_state(path)

        self.assertEqual(loaded.default_haul["station_1_buying"], "Aluminium")
        self.assertTrue(loaded.instant_mode)
        self.assertEqual(len(loaded.history), 1)
        self.assertEqual(loaded.history[0].raw, "haul Aluminium")
        self.assertEqual(loaded.history[0].params["dock_timeout"], "600.0")

    def test_loads_legacy_haul_defaults_key_for_backward_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            path.write_text('{"haul_defaults":{"station_1_buying":"Gold"},"history":[]}', encoding="utf-8")

            loaded = load_control_room_state(path)

        self.assertEqual(loaded.default_haul["station_1_buying"], "Gold")
        self.assertFalse(loaded.instant_mode)


if __name__ == "__main__":
    unittest.main()
