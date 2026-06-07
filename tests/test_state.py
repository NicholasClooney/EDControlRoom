from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
import os
import unittest

from edap.state import JournalWatcher, get_latest_journal_log, read_ship_state


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

    def test_read_ship_state_treats_location_docked_true_as_in_station(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "Journal.log"
            _write_lines(
                log_path,
                [
                    '{"event":"LoadGame","Ship":"type6"}',
                    '{"event":"SupercruiseExit","StarSystem":"Sol"}',
                    '{"event":"Died"}',
                    '{"event":"Resurrect","Option":"rebuy"}',
                    '{"event":"Location","Docked":true,"StarSystem":"Sol","StationName":"Abraham Lincoln"}',
                ],
            )
            os.utime(log_path, None)

            state = read_ship_state(log_path)

            self.assertEqual(state.status, "in_station")
            self.assertEqual(state.location, "Sol")

    def test_journal_watcher_starts_at_end_by_default_and_reads_appended_events(self) -> None:
        with TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            log_path = journal_dir / "Journal.01.log"
            _write_lines(log_path, ['{"event":"LoadGame"}'])
            sleep_calls: list[float] = []
            watcher = JournalWatcher(journal_dir, sleeper=sleep_calls.append)

            self.assertEqual(watcher.poll(), [])

            with log_path.open("a", encoding="utf-8") as handle:
                handle.write('{"event":"SupercruiseExit","StarSystem":"Sol"}\n')

            events = watcher.poll()

            self.assertEqual(events, [{"event": "SupercruiseExit", "StarSystem": "Sol"}])
            self.assertEqual(watcher.current_path, log_path)
            self.assertEqual(sleep_calls, [0.5])

    def test_journal_watcher_rolls_over_to_newer_log_and_resets_offset(self) -> None:
        with TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            first = journal_dir / "Journal.01.log"
            second = journal_dir / "Journal.02.log"
            _write_lines(first, ['{"event":"LoadGame"}'])
            os.utime(first, (time() - 20, time() - 20))
            watcher = JournalWatcher(journal_dir, initial_offset=0, sleeper=lambda _: None)

            first_events = watcher.poll()

            _write_lines(second, ['{"event":"SupercruiseExit"}'])
            os.utime(second, None)
            second_events = watcher.poll()

            self.assertEqual(first_events, [{"event": "LoadGame"}])
            self.assertEqual(second_events, [{"event": "SupercruiseExit"}])
            self.assertEqual(watcher.current_path, second)
            self.assertEqual(watcher.offset, second.stat().st_size)

    def test_journal_watcher_sleeps_when_idle(self) -> None:
        with TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            log_path = journal_dir / "Journal.01.log"
            _write_lines(log_path, ['{"event":"LoadGame"}'])
            sleep_calls: list[float] = []
            watcher = JournalWatcher(journal_dir, sleeper=sleep_calls.append)

            watcher.poll()
            events = watcher.poll()

            self.assertEqual(events, [])
            self.assertEqual(sleep_calls, [0.5, 0.5])
