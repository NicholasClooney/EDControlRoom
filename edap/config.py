from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys
import tomllib


DEFAULT_CONFIG_PATH = Path("config.toml")
EXAMPLE_CONFIG_PATH = Path("config.example.toml")
DEFAULT_TTS_CONFIG_PATH = Path(__file__).resolve().parent.parent / "defaults" / "tts.toml"
DEFAULT_ERROR_MESSAGES_CONFIG_PATH = Path(__file__).resolve().parent.parent / "defaults" / "error_messages.toml"

VALID_PLATFORMS = {"linux", "macos", "windows"}
VALID_CAPTURE_MODES = {"fullscreen", "region"}
VALID_TTS_TITLE_MODES = {"commander", "custom", "commander_name"}


def default_runtime_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform.startswith("win"):
        return "windows"
    raise ConfigError(
        "Config value `runtime.platform` must be set explicitly on this host. "
        "Supported runtime values are: linux, macos, windows."
    )


@dataclass(frozen=True)
class PathsConfig:
    journal_dir: Path | None
    bindings_file: Path | None


@dataclass(frozen=True)
class ControlsConfig:
    start_hotkey: str
    stop_hotkey: str
    scanner_mode: str
    minimum_action_hold_seconds: float
    continuous_action_hold_seconds: float
    step_delay_seconds: float
    galaxy_map_settle_seconds: float
    dock_supercruise_exit_settle_seconds: float
    haul_dock_timeout_seconds: float
    undock_timeout_seconds: float
    undock_no_track_timeout_seconds: float
    mass_lock_boost_delay_seconds: float
    market_nav_delay_seconds: float
    market_trade_max_attempts: int
    market_buy_hold_seconds_per_ton: float
    market_critical_level_multiplier: float
    haul_post_sell_settle_seconds: float
    haul_two_way_auto_hyperspace_engage: bool
    haul_two_way_open_nav_panel_after_hyperspace_arrival: bool
    haul_two_way_nav_panel_open_delay_seconds: float


@dataclass(frozen=True)
class ScreenConfig:
    resolution_width: int
    resolution_height: int
    scale: float
    capture_debug_path: Path | None
    capture: "CaptureConfig"


@dataclass(frozen=True)
class CaptureRegionConfig:
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class CaptureConfig:
    mode: str
    base_region: CaptureRegionConfig
    regions: dict[str, CaptureRegionConfig]


@dataclass(frozen=True)
class RuntimeConfig:
    platform: str
    debug: bool


@dataclass(frozen=True)
class ControlRoomConfig:
    state_file: Path
    history_limit: int
    activity_log_max_lines: int
    command_delay_seconds: float
    status_refresh_seconds: float = 2.0
    check_for_updates: bool = True


@dataclass(frozen=True)
class TTSConfig:
    enabled: bool = True
    title_mode: str = "commander"
    title: str = "commander"
    disabled_messages: tuple[str, ...] = ()
    phrases: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ErrorMessagesConfig:
    templates: dict[str, str] = field(default_factory=dict)


def default_error_messages_config() -> ErrorMessagesConfig:
    return ErrorMessagesConfig(templates=_string_dict(_load_default_error_messages_table(), "templates"))


@dataclass(frozen=True)
class AppConfig:
    paths: PathsConfig
    controls: ControlsConfig
    screen: ScreenConfig
    runtime: RuntimeConfig
    control_room: ControlRoomConfig
    tts: TTSConfig = field(default_factory=TTSConfig)
    error_messages: ErrorMessagesConfig = field(default_factory=default_error_messages_config)


class ConfigError(ValueError):
    """Raised when config parsing or validation fails."""


def _load_default_tts_table() -> dict[str, object]:
    with DEFAULT_TTS_CONFIG_PATH.open("rb") as handle:
        raw = tomllib.load(handle)
    if not isinstance(raw, dict):
        raise ConfigError("Default TTS config root must be a TOML table.")
    value = raw.get("tts", {})
    if not isinstance(value, dict):
        raise ConfigError("Default TTS config section `tts` must be a table.")
    return value


def _load_default_error_messages_table() -> dict[str, object]:
    with DEFAULT_ERROR_MESSAGES_CONFIG_PATH.open("rb") as handle:
        raw = tomllib.load(handle)
    if not isinstance(raw, dict):
        raise ConfigError("Default error-messages config root must be a TOML table.")
    value = raw.get("error_messages", {})
    if not isinstance(value, dict):
        raise ConfigError("Default error-messages config section `error_messages` must be a table.")
    return value


def _optional_path(value: object) -> Path | None:
    if not value:
        return None
    return Path(str(value)).expanduser()


def _require_table(raw: dict[str, object], key: str) -> dict[str, object]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"Config section `{key}` must be a table.")
    return value


def _optional_table(raw: dict[str, object], key: str) -> dict[str, object]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"Config section `{key}` must be a table.")
    return value


def _lookup_value(raw: dict[str, object], key: str, aliases: tuple[str, ...] = ()) -> object | None:
    if key in raw:
        return raw[key]
    for alias in aliases:
        if alias in raw:
            return raw[alias]
    return None


def _flatten_table(raw: dict[str, object], *, prefix: str = "") -> dict[str, object]:
    flattened: dict[str, object] = {}
    for key, value in raw.items():
        dotted_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flattened.update(_flatten_table(value, prefix=dotted_key))
            continue
        flattened[dotted_key] = value
    return flattened


def _string(raw: dict[str, object], key: str, default: str, *, aliases: tuple[str, ...] = ()) -> str:
    value = _lookup_value(raw, key, aliases)
    if value is None:
        value = default
    if not isinstance(value, str):
        raise ConfigError(f"Config value `{key}` must be a string.")
    return value


def _integer(raw: dict[str, object], key: str, default: int, *, aliases: tuple[str, ...] = ()) -> int:
    value = _lookup_value(raw, key, aliases)
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"Config value `{key}` must be an integer.")
    return value


def _float(raw: dict[str, object], key: str, default: float, *, aliases: tuple[str, ...] = ()) -> float:
    value = _lookup_value(raw, key, aliases)
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"Config value `{key}` must be a number.")
    return float(value)


def _boolean(raw: dict[str, object], key: str, default: bool, *, aliases: tuple[str, ...] = ()) -> bool:
    value = _lookup_value(raw, key, aliases)
    if value is None:
        value = default
    if not isinstance(value, bool):
        raise ConfigError(f"Config value `{key}` must be true or false.")
    return value


def _string_list(raw: dict[str, object], key: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list):
        raise ConfigError(f"Config value `{key}` must be a list of strings.")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigError(f"Config value `{key}[{index}]` must be a string.")
        result.append(item)
    return tuple(result)


def _string_dict(raw: dict[str, object], key: str) -> dict[str, str]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"Config section `{key}` must be a table.")
    result: dict[str, str] = {}
    for sub_key, sub_value in value.items():
        if not isinstance(sub_key, str) or not isinstance(sub_value, str):
            raise ConfigError(f"Config section `{key}` must contain only string values.")
        result[sub_key] = sub_value
    return result


def _validate_path_shape(path: Path | None, *, key: str, should_be_dir: bool) -> None:
    if path is None or not path.exists():
        return
    if should_be_dir and not path.is_dir():
        raise ConfigError(f"Config path `{key}` must point to a directory: {path}")
    if not should_be_dir and not path.is_file():
        raise ConfigError(f"Config path `{key}` must point to a file: {path}")


def _capture_region(
    raw: dict[str, object],
    defaults: tuple[float, float, float, float],
) -> CaptureRegionConfig:
    return CaptureRegionConfig(
        left=_float(raw, "left", defaults[0]),
        top=_float(raw, "top", defaults[1]),
        right=_float(raw, "right", defaults[2]),
        bottom=_float(raw, "bottom", defaults[3]),
    )


def _validate_capture_region(region: CaptureRegionConfig, *, key: str) -> None:
    for name, value in (
        ("left", region.left),
        ("top", region.top),
        ("right", region.right),
        ("bottom", region.bottom),
    ):
        if value < 0 or value > 1:
            raise ConfigError(f"Config value `{key}.{name}` must be between 0.0 and 1.0.")

    if region.left >= region.right:
        raise ConfigError(f"Config region `{key}` must have left < right.")
    if region.top >= region.bottom:
        raise ConfigError(f"Config region `{key}` must have top < bottom.")


def validate_config(config: AppConfig) -> AppConfig:
    if not config.controls.start_hotkey.strip():
        raise ConfigError("Config value `controls.start_hotkey` cannot be empty.")
    if not config.controls.stop_hotkey.strip():
        raise ConfigError("Config value `controls.stop_hotkey` cannot be empty.")
    if config.controls.minimum_action_hold_seconds <= 0:
        raise ConfigError("Config value `controls.minimum_action_hold_seconds` must be greater than 0.")
    if config.controls.continuous_action_hold_seconds <= 0:
        raise ConfigError("Config value `controls.continuous_action_hold_seconds` must be greater than 0.")
    if config.controls.continuous_action_hold_seconds < config.controls.minimum_action_hold_seconds:
        raise ConfigError(
            "Config value `controls.continuous_action_hold_seconds` must be greater than or equal to "
            "`controls.minimum_action_hold_seconds`."
        )
    if config.controls.step_delay_seconds < 0:
        raise ConfigError("Config value `controls.step_delay_seconds` must be non-negative.")
    if config.controls.galaxy_map_settle_seconds < 0:
        raise ConfigError("Config value `controls.galaxy_map_settle_seconds` must be non-negative.")
    if config.controls.dock_supercruise_exit_settle_seconds < 0:
        raise ConfigError("Config value `controls.dock_supercruise_exit_settle_seconds` must be non-negative.")
    if config.controls.haul_dock_timeout_seconds < 0:
        raise ConfigError("Config value `controls.haul_dock_timeout_seconds` must be non-negative.")
    if config.controls.undock_timeout_seconds < 0:
        raise ConfigError("Config value `controls.undock_timeout_seconds` must be non-negative.")
    if config.controls.undock_no_track_timeout_seconds < 0:
        raise ConfigError("Config value `controls.undock_no_track_timeout_seconds` must be non-negative.")
    if config.controls.mass_lock_boost_delay_seconds < 0:
        raise ConfigError("Config value `controls.mass_lock_boost_delay_seconds` must be non-negative.")
    if config.controls.market_nav_delay_seconds < 0:
        raise ConfigError("Config value `controls.market_nav_delay_seconds` must be non-negative.")
    if config.controls.market_trade_max_attempts < 1:
        raise ConfigError("Config value `controls.market_trade_max_attempts` must be at least 1.")
    if config.controls.market_buy_hold_seconds_per_ton <= 0:
        raise ConfigError(
            "Config value `controls.market_buy_hold_seconds_per_ton` must be greater than 0."
        )
    if config.controls.market_critical_level_multiplier <= 0:
        raise ConfigError("Config value `controls.market_critical_level_multiplier` must be greater than 0.")
    if config.controls.haul_post_sell_settle_seconds < 0:
        raise ConfigError("Config value `controls.haul_post_sell_settle_seconds` must be non-negative.")
    if config.controls.haul_two_way_nav_panel_open_delay_seconds < 0:
        raise ConfigError("Config value `controls.haul_two_way_nav_panel_open_delay_seconds` must be non-negative.")
    if config.screen.resolution_width <= 0:
        raise ConfigError("Config value `screen.resolution_width` must be greater than 0.")
    if config.screen.resolution_height <= 0:
        raise ConfigError("Config value `screen.resolution_height` must be greater than 0.")
    if config.screen.scale <= 0:
        raise ConfigError("Config value `screen.scale` must be greater than 0.")
    if config.screen.capture.mode not in VALID_CAPTURE_MODES:
        supported = ", ".join(sorted(VALID_CAPTURE_MODES))
        raise ConfigError(f"Config value `screen.capture.mode` must be one of: {supported}.")
    if config.runtime.platform.lower() not in VALID_PLATFORMS:
        supported = ", ".join(sorted(VALID_PLATFORMS))
        raise ConfigError(
            f"Config value `runtime.platform` must be one of: {supported}."
        )
    if config.control_room.history_limit <= 0:
        raise ConfigError("Config value `control_room.history_limit` must be greater than 0.")
    if config.control_room.activity_log_max_lines <= 0:
        raise ConfigError("Config value `control_room.activity_log_max_lines` must be greater than 0.")
    if config.control_room.command_delay_seconds < 0:
        raise ConfigError("Config value `control_room.command_delay_seconds` must be non-negative.")
    if config.control_room.status_refresh_seconds < 0:
        raise ConfigError("Config value `control_room.status_refresh_seconds` must be non-negative.")
    if config.tts.title_mode not in VALID_TTS_TITLE_MODES:
        supported = ", ".join(sorted(VALID_TTS_TITLE_MODES))
        raise ConfigError(f"Config value `tts.title_mode` must be one of: {supported}.")
    if config.tts.title_mode == "custom" and not config.tts.title.strip():
        raise ConfigError("Config value `tts.title` cannot be empty when `tts.title_mode` is `custom`.")

    _validate_path_shape(config.paths.journal_dir, key="paths.journal_dir", should_be_dir=True)
    _validate_path_shape(config.paths.bindings_file, key="paths.bindings_file", should_be_dir=False)
    if config.screen.capture_debug_path and config.screen.capture_debug_path.exists():
        if config.screen.capture_debug_path.is_dir():
            raise ConfigError(
                "Config value `screen.capture_debug_path` must point to a file, not a directory."
            )
    _validate_capture_region(config.screen.capture.base_region, key="screen.capture.base_region")
    for name, region in config.screen.capture.regions.items():
        if not name.strip():
            raise ConfigError("Config section `screen.capture.regions` cannot contain an empty name.")
        _validate_capture_region(region, key=f"screen.capture.regions.{name}")

    return config


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a TOML table.")

    paths = _require_table(raw, "paths")
    controls = _require_table(raw, "controls")
    controls_flat = _flatten_table(controls)
    screen = _require_table(raw, "screen")
    screen_capture = _optional_table(screen, "capture")
    screen_capture_regions = _optional_table(screen_capture, "regions")
    runtime = _require_table(raw, "runtime")
    control_room = _optional_table(raw, "control_room")
    tts = _optional_table(raw, "tts")
    error_messages = _optional_table(raw, "error_messages")
    default_tts = _load_default_tts_table()
    default_error_messages = _load_default_error_messages_table()

    capture_regions: dict[str, CaptureRegionConfig] = {
        "center": CaptureRegionConfig(
            left=1 / 3,
            top=1 / 3,
            right=2 / 3,
            bottom=2 / 3,
        ),
        "compass": CaptureRegionConfig(
            left=5 / 16,
            top=5 / 8,
            right=2 / 4,
            bottom=15 / 16,
        ),
    }
    for name, region_raw in screen_capture_regions.items():
        if not isinstance(name, str) or not isinstance(region_raw, dict):
            raise ConfigError("Config section `screen.capture.regions` must contain named tables.")
        capture_regions[name] = _capture_region(
            region_raw,
            (0.0, 0.0, 1.0, 1.0),
        )

    config = AppConfig(
        paths=PathsConfig(
            journal_dir=_optional_path(paths.get("journal_dir")),
            bindings_file=_optional_path(paths.get("bindings_file")),
        ),
        controls=ControlsConfig(
            start_hotkey=_string(controls_flat, "start_hotkey", "home"),
            stop_hotkey=_string(controls_flat, "stop_hotkey", "end"),
            scanner_mode=_string(controls_flat, "scanner_mode", "off"),
            minimum_action_hold_seconds=_float(
                controls_flat,
                "minimum_action_hold_seconds",
                0.1,
                aliases=("hold.minimum_action_seconds",),
            ),
            continuous_action_hold_seconds=_float(
                controls_flat,
                "continuous_action_hold_seconds",
                0.2,
                aliases=("hold.continuous_action_seconds",),
            ),
            step_delay_seconds=_float(
                controls_flat,
                "step_delay_seconds",
                0.3,
                aliases=("sequence.step_delay_seconds",),
            ),
            galaxy_map_settle_seconds=_float(
                controls_flat,
                "galaxy_map_settle_seconds",
                2.0,
                aliases=("galaxy_map.settle_seconds",),
            ),
            dock_supercruise_exit_settle_seconds=_float(
                controls_flat,
                "dock_supercruise_exit_settle_seconds",
                3.0,
                aliases=("dock.supercruise_exit_settle_seconds",),
            ),
            haul_dock_timeout_seconds=_float(
                controls_flat,
                "haul_dock_timeout_seconds",
                600.0,
                aliases=("haul.dock_timeout_seconds",),
            ),
            undock_timeout_seconds=_float(
                controls_flat,
                "undock_timeout_seconds",
                30.0,
                aliases=("undock.timeout_seconds",),
            ),
            undock_no_track_timeout_seconds=_float(
                controls_flat,
                "undock_no_track_timeout_seconds",
                600.0,
                aliases=("undock.no_track_timeout_seconds",),
            ),
            mass_lock_boost_delay_seconds=_float(
                controls_flat,
                "mass_lock_boost_delay_seconds",
                5.0,
                aliases=("mass_lock.boost_delay_seconds",),
            ),
            market_nav_delay_seconds=_float(
                controls_flat,
                "market_nav_delay_seconds",
                0.1,
                aliases=("market.nav_delay_seconds",),
            ),
            market_trade_max_attempts=_integer(
                controls_flat,
                "market_trade_max_attempts",
                3,
                aliases=("market.trade_max_attempts",),
            ),
            market_buy_hold_seconds_per_ton=_float(
                controls_flat,
                "market_buy_hold_seconds_per_ton",
                0.01,
                aliases=("market.buy_hold_seconds_per_ton",),
            ),
            market_critical_level_multiplier=_float(
                controls_flat,
                "market_critical_level_multiplier",
                10.0,
                aliases=("market.critical_level_multiplier",),
            ),
            haul_post_sell_settle_seconds=_float(
                controls_flat,
                "haul_post_sell_settle_seconds",
                2.0,
                aliases=("haul.post_sell_settle_seconds",),
            ),
            haul_two_way_auto_hyperspace_engage=_boolean(
                controls_flat,
                "haul_two_way_auto_hyperspace_engage",
                True,
                aliases=("haul.two_way.auto_hyperspace_engage",),
            ),
            haul_two_way_open_nav_panel_after_hyperspace_arrival=_boolean(
                controls_flat,
                "haul_two_way_open_nav_panel_after_hyperspace_arrival",
                True,
                aliases=("haul.two_way.open_nav_panel_after_hyperspace_arrival",),
            ),
            haul_two_way_nav_panel_open_delay_seconds=_float(
                controls_flat,
                "haul_two_way_nav_panel_open_delay_seconds",
                3.0,
                aliases=("haul.two_way.nav_panel_open_delay_seconds",),
            ),
        ),
        screen=ScreenConfig(
            resolution_width=_integer(screen, "resolution_width", 1920),
            resolution_height=_integer(screen, "resolution_height", 1080),
            scale=_float(screen, "scale", 1.0),
            capture_debug_path=_optional_path(screen.get("capture_debug_path")),
            capture=CaptureConfig(
                mode=_string(screen_capture, "mode", "fullscreen"),
                base_region=_capture_region(
                    screen_capture,
                    (0.0, 0.0, 1.0, 1.0),
                ),
                regions=capture_regions,
            ),
        ),
        runtime=RuntimeConfig(
            platform=_string(runtime, "platform", default_runtime_platform()),
            debug=_boolean(runtime, "debug", True),
        ),
        control_room=ControlRoomConfig(
            state_file=Path(_string(control_room, "state_file", ".control_room_state.json")).expanduser(),
            history_limit=_integer(control_room, "history_limit", 20),
            activity_log_max_lines=_integer(control_room, "activity_log_max_lines", 2000),
            command_delay_seconds=_float(control_room, "command_delay_seconds", 5.0),
            status_refresh_seconds=_float(control_room, "status_refresh_seconds", 2.0),
            check_for_updates=_boolean(control_room, "check_for_updates", True),
        ),
        tts=TTSConfig(
            enabled=_boolean(tts, "enabled", _boolean(default_tts, "enabled", True)),
            title_mode=_string(tts, "title_mode", _string(default_tts, "title_mode", "commander")),
            title=_string(tts, "title", _string(default_tts, "title", "commander")),
            disabled_messages=(
                _string_list(tts, "disabled_messages")
                if "disabled_messages" in tts
                else _string_list(default_tts, "disabled_messages")
            ),
            phrases={
                **_string_dict(default_tts, "phrases"),
                **_string_dict(tts, "phrases"),
            },
        ),
        error_messages=ErrorMessagesConfig(
            templates={
                **_string_dict(default_error_messages, "templates"),
                **_string_dict(error_messages, "templates"),
            },
        ),
    )
    return validate_config(config)
