from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from edap.config import ConfigError, load_config


def _write_config(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


class LoadConfigTests(unittest.TestCase):
    def test_loads_valid_config_with_defaults(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[runtime]
""".strip(),
            )

            config = load_config(config_path)

            self.assertIsNone(config.paths.journal_dir)
            self.assertIsNone(config.paths.bindings_file)
            self.assertEqual(config.controls.start_hotkey, "home")
            self.assertEqual(config.controls.stop_hotkey, "end")
            self.assertEqual(config.screen.resolution_width, 1920)
            self.assertEqual(config.runtime.platform, "macos")

    def test_rejects_unsupported_platform(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[runtime]
platform = "linux"
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "runtime.platform"):
                load_config(config_path)

    def test_rejects_existing_bindings_directory_when_file_expected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bindings_dir = temp_path / "Bindings"
            bindings_dir.mkdir()
            config_path = temp_path / "config.toml"
            _write_config(
                config_path,
                f"""
[paths]
bindings_file = "{bindings_dir}"

[controls]

[screen]

[runtime]
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "paths.bindings_file"):
                load_config(config_path)

    def test_rejects_boolean_for_integer_setting(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]
resolution_width = true

[runtime]
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "resolution_width"):
                load_config(config_path)
