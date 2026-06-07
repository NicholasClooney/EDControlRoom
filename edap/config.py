from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


DEFAULT_CONFIG_PATH = Path("config.toml")
EXAMPLE_CONFIG_PATH = Path("config.example.toml")

VALID_PLATFORMS = {"macos", "windows"}
VALID_CAPTURE_MODES = {"fullscreen", "region"}


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
    haul_dock_timeout_seconds: float
    undock_timeout_seconds: float


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


@dataclass(frozen=True)
class AppConfig:
    paths: PathsConfig
    controls: ControlsConfig
    screen: ScreenConfig
    runtime: RuntimeConfig
    control_room: ControlRoomConfig


class ConfigError(ValueError):
    """Raised when config parsing or validation fails."""


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


def _string(raw: dict[str, object], key: str, default: str) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"Config value `{key}` must be a string.")
    return value


def _integer(raw: dict[str, object], key: str, default: int) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"Config value `{key}` must be an integer.")
    return value


def _float(raw: dict[str, object], key: str, default: float) -> float:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"Config value `{key}` must be a number.")
    return float(value)


def _boolean(raw: dict[str, object], key: str, default: bool) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"Config value `{key}` must be true or false.")
    return value


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
    if config.controls.haul_dock_timeout_seconds < 0:
        raise ConfigError("Config value `controls.haul_dock_timeout_seconds` must be non-negative.")
    if config.controls.undock_timeout_seconds < 0:
        raise ConfigError("Config value `controls.undock_timeout_seconds` must be non-negative.")
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
    screen = _require_table(raw, "screen")
    screen_capture = _optional_table(screen, "capture")
    screen_capture_regions = _optional_table(screen_capture, "regions")
    runtime = _require_table(raw, "runtime")
    control_room = _optional_table(raw, "control_room")

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
            start_hotkey=_string(controls, "start_hotkey", "home"),
            stop_hotkey=_string(controls, "stop_hotkey", "end"),
            scanner_mode=_string(controls, "scanner_mode", "off"),
            minimum_action_hold_seconds=_float(controls, "minimum_action_hold_seconds", 0.1),
            continuous_action_hold_seconds=_float(controls, "continuous_action_hold_seconds", 0.2),
            step_delay_seconds=_float(controls, "step_delay_seconds", 0.3),
            galaxy_map_settle_seconds=_float(controls, "galaxy_map_settle_seconds", 2.0),
            haul_dock_timeout_seconds=_float(controls, "haul_dock_timeout_seconds", 600.0),
            undock_timeout_seconds=_float(controls, "undock_timeout_seconds", 30.0),
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
            platform=_string(runtime, "platform", "macos"),
            debug=_boolean(runtime, "debug", True),
        ),
        control_room=ControlRoomConfig(
            state_file=Path(_string(control_room, "state_file", ".control_room_state.json")).expanduser(),
            history_limit=_integer(control_room, "history_limit", 20),
        ),
    )
    return validate_config(config)
