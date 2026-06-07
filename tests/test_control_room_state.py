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

        self.assertEqual(state.haul_defaults, {})
        self.assertEqual(state.dest_defaults, {})
        self.assertEqual(state.history, [])

    def test_save_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            original = ControlRoomState(
                haul_defaults={"commodity": "Aluminium", "buy_station": "Hutton Orbital"},
                dest_defaults={"galaxy_map_settle": 5.0},
                history=[
                    CommandHistoryEntry(
                        raw="haul Aluminium",
                        command="haul",
                        params={"commodity": "Aluminium", "dock_timeout": "600.0"},
                        timestamp="2026-06-07T12:00:00Z",
                    )
                ],
            )

            save_control_room_state(path, original)
            loaded = load_control_room_state(path)

        self.assertEqual(loaded.haul_defaults["commodity"], "Aluminium")
        self.assertEqual(loaded.dest_defaults["galaxy_map_settle"], 5.0)
        self.assertEqual(len(loaded.history), 1)
        self.assertEqual(loaded.history[0].raw, "haul Aluminium")
        self.assertEqual(loaded.history[0].params["dock_timeout"], "600.0")


if __name__ == "__main__":
    unittest.main()
