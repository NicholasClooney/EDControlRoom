from __future__ import annotations

from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
import os
import unittest
from unittest.mock import patch

from edap.platform.paths.linux import LinuxGamePaths
from edap.platform.paths.macos import MacOSGamePaths
from edap.platform.paths.windows import WindowsGamePaths


class _TestableMacOSGamePaths(MacOSGamePaths):
    def __init__(self, roots: list[Path]) -> None:
        self._roots = roots

    def _crossover_roots(self) -> list[Path]:
        return self._roots


class MacOSGamePathsTests(unittest.TestCase):
    def test_default_bindings_file_picks_newest_candidate_by_mtime(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            older = root / "BottleA/drive_c/users/crossover/AppData/Local/Frontier Developments/Elite Dangerous/Options/Bindings/Old.binds"
            newer = root / "BottleB/drive_c/users/crossover/Local Settings/Application Data/Frontier Developments/Elite Dangerous/Options/Bindings/New.binds"
            older.parent.mkdir(parents=True)
            newer.parent.mkdir(parents=True)
            older.write_text("<Root />", encoding="utf-8")
            newer.write_text("<Root />", encoding="utf-8")
            os.utime(older, (time() - 40, time() - 40))
            os.utime(newer, (time() - 10, time() - 10))

            game_paths = _TestableMacOSGamePaths([root])

            selected = game_paths.default_bindings_file()
            report = game_paths.describe_bindings_discovery()

            self.assertEqual(selected, newer)
            self.assertEqual(report["selected_path"], str(newer))
            self.assertEqual(report["status"], "ok")

    def test_default_journal_dir_finds_cross_over_saved_games_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            journal_dir = root / "BottleA/drive_c/users/crossover/Saved Games/Frontier Developments/Elite Dangerous"
            journal_dir.mkdir(parents=True)

            game_paths = _TestableMacOSGamePaths([root])

            selected = game_paths.default_journal_dir()
            report = game_paths.describe_journal_discovery()

            self.assertEqual(selected, journal_dir)
            self.assertEqual(report["selected_path"], str(journal_dir))
            self.assertEqual(report["status"], "ok")


class WindowsGamePathsTests(unittest.TestCase):
    def test_defaults_return_none_without_environment(self) -> None:
        with patch.dict(environ, {}, clear=True):
            game_paths = WindowsGamePaths()

            self.assertIsNone(game_paths.default_journal_dir())
            self.assertIsNone(game_paths.default_bindings_file())

    def test_default_bindings_file_uses_newest_candidate_by_mtime(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            localappdata = root / "LocalAppData"
            bindings_dir = localappdata / "Frontier Developments/Elite Dangerous/Options/Bindings"
            bindings_dir.mkdir(parents=True)
            newer = bindings_dir / "A.binds"
            older = bindings_dir / "Z.binds"
            older.write_text("<Root />", encoding="utf-8")
            newer.write_text("<Root />", encoding="utf-8")
            os.utime(older, (time() - 40, time() - 40))
            os.utime(newer, (time() - 10, time() - 10))

            with patch.dict(environ, {"LOCALAPPDATA": str(localappdata)}, clear=True):
                selected = WindowsGamePaths().default_bindings_file()

            self.assertEqual(selected, newer)


class _TestableLinuxGamePaths(LinuxGamePaths):
    def __init__(self, roots: list[Path]) -> None:
        self._roots = roots

    def _steam_roots(self) -> list[Path]:
        return self._roots


class LinuxGamePathsTests(unittest.TestCase):
    def test_default_journal_dir_finds_proton_saved_games_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            journal_dir = (
                root
                / "steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous"
            )
            journal_dir.mkdir(parents=True)

            game_paths = _TestableLinuxGamePaths([root])

            selected = game_paths.default_journal_dir()
            report = game_paths.describe_journal_discovery()

            self.assertEqual(selected, journal_dir)
            self.assertEqual(report["selected_path"], str(journal_dir))
            self.assertEqual(report["status"], "ok")

    def test_default_bindings_file_picks_newest_candidate_by_mtime(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            older = (
                root
                / "steamapps/compatdata/359320/pfx/drive_c/users/steamuser/AppData/Local/Frontier Developments/Elite Dangerous/Options/Bindings/Old.binds"
            )
            newer = (
                root
                / "steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Local Settings/Application Data/Frontier Developments/Elite Dangerous/Options/Bindings/New.binds"
            )
            older.parent.mkdir(parents=True)
            newer.parent.mkdir(parents=True)
            older.write_text("<Root />", encoding="utf-8")
            newer.write_text("<Root />", encoding="utf-8")
            os.utime(older, (time() - 40, time() - 40))
            os.utime(newer, (time() - 10, time() - 10))

            game_paths = _TestableLinuxGamePaths([root])

            selected = game_paths.default_bindings_file()
            report = game_paths.describe_bindings_discovery()

            self.assertEqual(selected, newer)
            self.assertEqual(report["selected_path"], str(newer))
            self.assertEqual(report["status"], "ok")
