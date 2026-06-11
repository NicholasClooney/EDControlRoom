from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from edap.capture import build_capture_layout
from edap.config import ConfigError, default_runtime_platform, load_config


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

            with patch("edap.config.default_runtime_platform", return_value="macos"):
                config = load_config(config_path)

            self.assertIsNone(config.paths.journal_dir)
            self.assertIsNone(config.paths.bindings_file)
            self.assertEqual(config.controls.start_hotkey, "home")
            self.assertEqual(config.controls.stop_hotkey, "end")
            self.assertEqual(config.controls.minimum_action_hold_seconds, 0.1)
            self.assertEqual(config.controls.continuous_action_hold_seconds, 0.2)
            self.assertEqual(config.controls.galaxy_map_settle_seconds, 2.0)
            self.assertEqual(config.controls.dock_supercruise_exit_settle_seconds, 3.0)
            self.assertEqual(config.controls.haul_dock_timeout_seconds, 600.0)
            self.assertEqual(config.controls.undock_timeout_seconds, 30.0)
            self.assertEqual(config.controls.undock_no_track_timeout_seconds, 600.0)
            self.assertEqual(config.controls.market_buy_hold_seconds_per_ton, 0.01)
            self.assertEqual(config.controls.market_critical_level_multiplier, 10.0)
            self.assertTrue(config.controls.haul_two_way_auto_hyperspace_engage)
            self.assertTrue(config.controls.haul_two_way_open_nav_panel_after_hyperspace_arrival)
            self.assertEqual(config.controls.haul_two_way_nav_panel_open_delay_seconds, 3.0)
            self.assertEqual(config.screen.resolution_width, 1920)
            self.assertEqual(config.screen.capture.mode, "fullscreen")
            self.assertIn("center", config.screen.capture.regions)
            self.assertEqual(config.runtime.platform, "macos")
            self.assertEqual(config.control_room.state_file, Path(".control_room_state.json"))
            self.assertEqual(config.control_room.history_limit, 20)
            self.assertEqual(config.control_room.activity_log_max_lines, 2000)
            self.assertEqual(config.control_room.command_delay_seconds, 5.0)
            self.assertEqual(config.control_room.status_refresh_seconds, 2.0)
            self.assertTrue(config.control_room.check_for_updates)
            self.assertTrue(config.tts.enabled)
            self.assertEqual(config.tts.title_mode, "commander")
            self.assertEqual(config.tts.title, "commander")
            self.assertEqual(config.tts.phrases["destination_set"], "Setting destination to {system_name}.")
            self.assertEqual(
                config.tts.phrases["auto_docking_engaged"],
                "Engaging auto docking sequence.",
            )
            self.assertEqual(
                config.tts.phrases["ship_serviced"],
                "Ship is fully fueled up and repaired, {title}.",
            )
            self.assertEqual(
                config.error_messages.templates["station_mismatch_message"],
                "Station mismatch: market data indicates {market_station}, but we are docked at {docked_station}.",
            )

    def test_error_message_partial_override_keeps_default_templates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[runtime]

[error_messages.templates]
station_mismatch_message = "Market data says {market_station}; docked station says {docked_station}."
""".strip(),
            )

            config = load_config(config_path)

            self.assertEqual(
                config.error_messages.templates["station_mismatch_message"],
                "Market data says {market_station}; docked station says {docked_station}.",
            )
            self.assertEqual(
                config.error_messages.templates["route_mismatch_suggestion"],
                "Use Ctrl-R then e to edit the destination or haul parameters, or start a new haul with the correct route.",
            )

    def test_tts_partial_override_keeps_default_phrases(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[runtime]

[tts]
title_mode = "custom"
title = "captain"
disabled_messages = ["arrival"]

[tts.phrases]
station_cleared = "Station cleared, {title}."
""".strip(),
            )

            config = load_config(config_path)

            self.assertEqual(config.tts.title_mode, "custom")
            self.assertEqual(config.tts.title, "captain")
            self.assertEqual(config.tts.disabled_messages, ("arrival",))
            self.assertEqual(config.tts.phrases["station_cleared"], "Station cleared, {title}.")
            self.assertEqual(
                config.tts.phrases["haul_aborted"],
                "Haul aborted.",
            )
            self.assertEqual(config.tts.phrases["destination_set"], "Setting destination to {system_name}.")

    def test_loads_nested_control_section_overrides(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]
start_hotkey = "pageup"

[controls.hold]
minimum_action_seconds = 0.15
continuous_action_seconds = 0.25

[controls.market]
nav_delay_seconds = 0.2
trade_max_attempts = 5

[controls.haul.two_way]
auto_hyperspace_engage = false
nav_panel_open_delay_seconds = 4.0

[screen]

[runtime]
""".strip(),
            )

            config = load_config(config_path)

            self.assertEqual(config.controls.start_hotkey, "pageup")
            self.assertEqual(config.controls.minimum_action_hold_seconds, 0.15)
            self.assertEqual(config.controls.continuous_action_hold_seconds, 0.25)
            self.assertEqual(config.controls.market_nav_delay_seconds, 0.2)
            self.assertEqual(config.controls.market_trade_max_attempts, 5)
            self.assertFalse(config.controls.haul_two_way_auto_hyperspace_engage)
            self.assertEqual(config.controls.haul_two_way_nav_panel_open_delay_seconds, 4.0)

    def test_loads_control_room_update_check_override(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[runtime]

[control_room]
check_for_updates = false
""".strip(),
            )

            config = load_config(config_path)

            self.assertFalse(config.control_room.check_for_updates)

    def test_loads_control_room_activity_log_limit_override(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[runtime]

[control_room]
activity_log_max_lines = 500
""".strip(),
            )

            config = load_config(config_path)

            self.assertEqual(config.control_room.activity_log_max_lines, 500)

    def test_defaults_runtime_platform_from_host_when_omitted(self) -> None:
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

            with patch("edap.config.default_runtime_platform", return_value="windows"):
                config = load_config(config_path)

            self.assertEqual(config.runtime.platform, "windows")

    def test_tts_commander_name_mode_allows_blank_custom_title(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[runtime]

[tts]
title_mode = "commander_name"
title = ""
""".strip(),
            )

            config = load_config(config_path)

            self.assertEqual(config.tts.title_mode, "commander_name")
            self.assertEqual(config.tts.title, "")

    def test_rejects_unknown_tts_title_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[runtime]

[tts]
title_mode = "invalid"
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "tts.title_mode"):
                load_config(config_path)

    def test_rejects_blank_custom_tts_title(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[runtime]

[tts]
title_mode = "custom"
title = ""
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "tts.title"):
                load_config(config_path)

    def test_rejects_omitted_runtime_platform_on_unsupported_host(self) -> None:
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

            with patch(
                "edap.config.default_runtime_platform",
                side_effect=ConfigError("Config value `runtime.platform` must be set explicitly on this host."),
            ):
                with self.assertRaisesRegex(ConfigError, "runtime.platform"):
                    load_config(config_path)

    def test_default_runtime_platform_maps_supported_hosts(self) -> None:
        with patch("edap.config.sys.platform", "darwin"):
            self.assertEqual(default_runtime_platform(), "macos")
        with patch("edap.config.sys.platform", "linux"):
            self.assertEqual(default_runtime_platform(), "linux")
        with patch("edap.config.sys.platform", "win32"):
            self.assertEqual(default_runtime_platform(), "windows")

    def test_default_runtime_platform_rejects_unsupported_host(self) -> None:
        with patch("edap.config.sys.platform", "freebsd13"):
            with self.assertRaisesRegex(ConfigError, "runtime.platform"):
                default_runtime_platform()

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

    def test_rejects_negative_control_room_command_delay(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[runtime]

[control_room]
command_delay_seconds = -0.1
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "control_room.command_delay_seconds"):
                load_config(config_path)

    def test_rejects_negative_control_room_status_refresh(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[runtime]

[control_room]
status_refresh_seconds = -0.1
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "control_room.status_refresh_seconds"):
                load_config(config_path)

    def test_rejects_non_positive_control_room_activity_log_limit(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]

[screen]

[runtime]

[control_room]
activity_log_max_lines = 0
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "control_room.activity_log_max_lines"):
                load_config(config_path)

    def test_rejects_non_positive_market_critical_level_multiplier(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]
market_critical_level_multiplier = 0

[screen]

[runtime]
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "market_critical_level_multiplier"):
                load_config(config_path)

    def test_rejects_non_positive_market_buy_hold_seconds_per_ton(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_config(
                config_path,
                """
[paths]

[controls]
market_buy_hold_seconds_per_ton = 0

[screen]

[runtime]
""".strip(),
            )

            with self.assertRaisesRegex(ConfigError, "market_buy_hold_seconds_per_ton"):
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
platform = "plan9"
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
bindings_file = '{bindings_dir}'

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
