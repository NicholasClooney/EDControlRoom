from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
import os
import unittest

from edap.state import get_latest_journal_log, read_ship_state


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class StateTests(unittest.TestCase):
    def test_get_latest_journal_log_picks_newest_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            older = journal_dir / "Journal.01.log"
            newer = journal_dir / "Journal.02.log"
            _write_lines(older, ['{"event":"LoadGame"}'])
            _write_lines(newer, ['{"event":"LoadGame"}'])
            os.utime(older, (time() - 20, time() - 20))
            os.utime(newer, (time() - 5, time() - 5))

            latest = get_latest_journal_log(journal_dir)

            self.assertEqual(latest, newer)

    def test_read_ship_state_extracts_status_target_and_fuel(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "Journal.log"
            _write_lines(
                log_path,
                [
                    '{"event":"LoadGame","Ship":"type6","FuelLevel":8.0,"FuelCapacity":{"Main":16.0}}',
                    '{"event":"Location","Docked":false,"StarSystem":"Sol","FuelLevel":8.0,"FuelCapacity":16.0}',
                    '{"event":"FSDTarget","Name":"Achenar"}',
                    '{"event":"StartJump","JumpType":"Hyperspace","StarClass":"K"}',
                    '{"event":"FuelScoop","Total":15.0}',
                ],
            )
            os.utime(log_path, None)

            state = read_ship_state(log_path)

            self.assertEqual(state.ship_type, "type6")
            self.assertEqual(state.location, "Sol")
            self.assertEqual(state.target, "Achenar")
            self.assertEqual(state.status, "starting_hyperspace")
            self.assertEqual(state.star_class, "K")
            self.assertEqual(state.fuel_capacity, 16.0)
            self.assertEqual(state.fuel_level, 15.0)
            self.assertEqual(state.fuel_percent, 94)
            self.assertTrue(state.is_scooping)
            self.assertGreaterEqual(state.time_since_log_update_s, 0)
