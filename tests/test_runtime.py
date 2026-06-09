from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from edap.config import load_config
from edap.platform.input.linux import LinuxInputController
from edap.runtime import build_runtime_context, load_config_with_fallback
from edap.platform.input.windows import WindowsInputController


class _FakeGamePaths:
    def __init__(self, journal_dir: Path | None = None, bindings_file: Path | None = None) -> None:
        self._journal_dir = journal_dir
        self._bindings_file = bindings_file

    def default_journal_dir(self) -> Path | None:
        return self._journal_dir

    def default_bindings_file(self) -> Path | None:
        return self._bindings_file


class RuntimeTests(unittest.TestCase):
    def test_load_config_with_fallback_uses_example_for_default_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            default_config_path = temp_root / "config.toml"
            example_path = temp_root / "config.example.toml"
            example_path.write_text(
                """
[paths]

[controls]

[screen]

[runtime]
""".strip(),
                encoding="utf-8",
            )

            with patch("edap.runtime.DEFAULT_CONFIG_PATH", default_config_path), patch(
                "edap.runtime.EXAMPLE_CONFIG_PATH",
                example_path,
            ), patch("edap.config.default_runtime_platform", return_value="macos"):
                loaded = load_config_with_fallback(default_config_path)

        self.assertEqual(loaded.config_path, str(example_path))
        self.assertTrue(loaded.used_example_config_fallback)
        self.assertEqual(loaded.config.runtime.platform, "macos")

    def test_build_runtime_context_prefers_configured_paths_and_loads_lookup(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            journal_dir = temp_root / "Journal"
            bindings_file = temp_root / "Custom.binds"
            journal_dir.mkdir()
            bindings_file.write_text("<Root />", encoding="utf-8")
            config_path = temp_root / "config.toml"
            config_path.write_text(
                f"""
[paths]
journal_dir = '{journal_dir}'
bindings_file = '{bindings_file}'

[controls]

[screen]

[runtime]
""".strip(),
                encoding="utf-8",
            )
            config = load_config(config_path)

            with patch("edap.runtime.build_game_paths", return_value=None), patch(
                "edap.runtime.build_input_controller",
                return_value=object(),
            ), patch(
                "edap.runtime.build_screen_capture",
                return_value=object(),
            ), patch(
                "edap.runtime.load_binding_lookup",
                return_value=object(),
            ) as load_binding_lookup_mock:
                runtime = build_runtime_context(config, actions=["SetSpeedZero"])

        self.assertEqual(runtime.journal.effective["source"], "configured")
        self.assertEqual(runtime.journal.effective_path, journal_dir)
        self.assertEqual(runtime.bindings.effective["source"], "configured")
        self.assertEqual(runtime.bindings.effective_path, bindings_file)
        self.assertIsNotNone(runtime.binding_lookup)
        load_binding_lookup_mock.assert_called_once_with(bindings_file, actions=["SetSpeedZero"])

    def test_build_runtime_context_uses_auto_detected_bindings_when_unconfigured(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            auto_journal_dir = temp_root / "Saved Games/Frontier Developments/Elite Dangerous"
            auto_bindings_file = temp_root / "Bindings/Custom.binds"
            auto_journal_dir.mkdir(parents=True)
            auto_bindings_file.parent.mkdir(parents=True)
            auto_bindings_file.write_text("<Root />", encoding="utf-8")
            config_path = temp_root / "config.toml"
            config_path.write_text(
                """
[paths]

[controls]

[screen]

[runtime]
""".strip(),
                encoding="utf-8",
            )
            config = load_config(config_path)
            game_paths = _FakeGamePaths(
                journal_dir=auto_journal_dir,
                bindings_file=auto_bindings_file,
            )

            with patch("edap.runtime.build_game_paths", return_value=game_paths), patch(
                "edap.runtime.build_input_controller",
                return_value=None,
            ), patch(
                "edap.runtime.build_screen_capture",
                return_value=None,
            ):
                runtime = build_runtime_context(config)

        self.assertEqual(runtime.journal.effective["source"], "auto_detected")
        self.assertEqual(runtime.journal.effective_path, auto_journal_dir)
        self.assertEqual(runtime.bindings.cli_source_status(), "auto_detected")
        self.assertEqual(runtime.bindings.effective_path, auto_bindings_file)
        self.assertIsNone(runtime.binding_lookup)

    def test_build_runtime_context_skips_screen_capture_by_default(self) -> None:
        config = load_config("config.example.toml")

        with patch("edap.runtime.build_game_paths", return_value=None), patch(
            "edap.runtime.build_input_controller",
            return_value=object(),
        ), patch(
            "edap.runtime.build_screen_capture",
        ) as build_screen_capture_mock:
            runtime = build_runtime_context(config, actions=["SetSpeedZero"])

        self.assertIsNone(runtime.screen_capture)
        build_screen_capture_mock.assert_not_called()

    def test_build_runtime_context_reports_missing_configured_bindings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            missing_bindings = temp_root / "Missing.binds"
            config_path = temp_root / "config.toml"
            config_path.write_text(
                f"""
[paths]
bindings_file = '{missing_bindings}'

[controls]

[screen]

[runtime]
""".strip(),
                encoding="utf-8",
            )
            config = load_config(config_path)

            with patch("edap.runtime.build_game_paths", return_value=None), patch(
                "edap.runtime.build_input_controller",
                return_value=None,
            ), patch(
                "edap.runtime.build_screen_capture",
                return_value=None,
            ):
                runtime = build_runtime_context(config, actions=["SetSpeedZero"])

        self.assertEqual(runtime.bindings.effective["status"], "missing")
        self.assertEqual(runtime.bindings.cli_source_status(), "configured_missing")
        self.assertIsNone(runtime.binding_lookup)

    def test_build_runtime_context_builds_windows_input_controller(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            config_path = temp_root / "config.toml"
            config_path.write_text(
                """
[paths]

[controls]

[screen]

[runtime]
platform = "windows"
""".strip(),
                encoding="utf-8",
            )
            config = load_config(config_path)

            with patch("edap.runtime.build_game_paths", return_value=None), patch(
                "edap.runtime.build_screen_capture",
                return_value=None,
            ):
                runtime = build_runtime_context(config)

        self.assertIsInstance(runtime.input_controller, WindowsInputController)

    def test_build_runtime_context_builds_linux_input_controller(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            config_path = temp_root / "config.toml"
            config_path.write_text(
                """
[paths]

[controls]

[screen]

[runtime]
platform = "linux"
""".strip(),
                encoding="utf-8",
            )
            config = load_config(config_path)

            with patch("edap.runtime.build_game_paths", return_value=None), patch(
                "edap.runtime.build_screen_capture",
                return_value=None,
            ):
                runtime = build_runtime_context(config)

        self.assertIsInstance(runtime.input_controller, LinuxInputController)
