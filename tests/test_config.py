from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from edap.capture import build_capture_layout
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
            self.assertEqual(config.controls.minimum_action_hold_seconds, 0.1)
            self.assertEqual(config.controls.continuous_action_hold_seconds, 0.2)
            self.assertEqual(config.controls.galaxy_map_settle_seconds, 2.0)
            self.assertEqual(config.screen.resolution_width, 1920)
            self.assertEqual(config.screen.capture.mode, "fullscreen")
            self.assertIn("center", config.screen.capture.regions)
            self.assertEqual(config.runtime.platform, "macos")

    def test_rejects_non_positive_continuous_hold_setting(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]
continuous_action_hold_seconds = 0.0

[screen]

[runtime]
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "continuous_action_hold_seconds"):
                load_config(config_path)

    def test_rejects_non_positive_minimum_hold_setting(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]
minimum_action_hold_seconds = 0.0

[screen]

[runtime]
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "minimum_action_hold_seconds"):
                load_config(config_path)

    def test_rejects_continuous_hold_below_minimum_hold(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]
minimum_action_hold_seconds = 0.15
continuous_action_hold_seconds = 0.1

[screen]

[runtime]
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "continuous_action_hold_seconds"):
                load_config(config_path)

    def test_loads_capture_region_overrides(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]
resolution_width = 2560
resolution_height = 1440
scale = 2.0

[screen.capture]
mode = "region"
left = 0.1
top = 0.2
right = 0.9
bottom = 0.8

[screen.capture.regions.nav]
left = 0.25
top = 0.5
right = 0.75
bottom = 0.9

[runtime]
""".strip(),
            )

            config = load_config(config_path)
            layout = build_capture_layout(config.screen)

            self.assertEqual(config.screen.capture.mode, "region")
            self.assertEqual(layout.reference_width, 5120)
            self.assertEqual(layout.reference_height, 2880)
            self.assertEqual(layout.base_bounds.left, 512)
            self.assertEqual(layout.base_bounds.top, 576)
            self.assertEqual(layout.base_bounds.right, 4608)
            self.assertEqual(layout.base_bounds.bottom, 2304)
            self.assertEqual(layout.named_regions["nav"].width, 2048)

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

    def test_rejects_invalid_capture_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[screen.capture]
mode = "weird"

[runtime]
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "screen.capture.mode"):
                load_config(config_path)

    def test_rejects_out_of_range_capture_region(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[screen.capture]
left = 1.1

[runtime]
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "screen.capture.base_region.left"):
                load_config(config_path)
