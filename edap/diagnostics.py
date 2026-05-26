from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from time import sleep

from edap.bindings import read_bindings
from edap.capture import build_capture_layout
from edap.config import AppConfig
from edap.platform.input.factory import build_input_controller
from edap.platform.paths.factory import build_game_paths
from edap.platform.screen.factory import build_screen_capture
from edap.state import get_latest_journal_log, read_ship_state


@dataclass(frozen=True)
class DiagnosticsOptions:
    capture_screen: bool = False
    send_test_key: bool = False
    test_key: str = "space"
    test_modifier: str | None = None
    hold_s: float = 0.0
    delay_s: float = 0.0
    repeat: int = 1


def _configured_path_report(path: Path | None, *, kind: str) -> dict[str, object]:
    if path is None:
        return {
            "path": None,
            "status": "not_configured",
            "reason": f"no explicit {kind} configured",
        }

    if not path.exists():
        return {
            "path": str(path),
            "status": "missing",
            "reason": f"configured {kind} path does not exist",
        }

    if kind == "journal directory" and not path.is_dir():
        return {
            "path": str(path),
            "status": "invalid",
            "reason": "configured journal path exists but is not a directory",
        }

    if kind == "bindings file" and not path.is_file():
        return {
            "path": str(path),
            "status": "invalid",
            "reason": "configured bindings path exists but is not a file",
        }

    return {
        "path": str(path),
        "status": "ok",
        "reason": f"using configured {kind}",
    }


def _autodetected_path_report(game_paths: object, *, kind: str) -> dict[str, object]:
    describe_name = "describe_journal_discovery" if kind == "journal" else "describe_bindings_discovery"
    if game_paths is not None and hasattr(game_paths, describe_name):
        report = getattr(game_paths, describe_name)()
        return dict(report)

    detected_path = None
    if game_paths is not None:
        detected_path = (
            game_paths.default_journal_dir() if kind == "journal" else game_paths.default_bindings_file()
        )

    if detected_path is None:
        return {
            "path": None,
            "status": "unsupported",
            "reason": "platform backend did not provide auto-detection details",
        }

    return {
        "path": str(detected_path),
        "status": "ok",
        "reason": "auto-detected default path",
    }


def _effective_path_report(
    configured: dict[str, object],
    autodetected: dict[str, object],
) -> dict[str, object]:
    if configured["status"] == "ok":
        return {
            "path": configured["path"],
            "status": "ok",
            "source": "configured",
            "reason": configured["reason"],
        }

    autodetected_path = autodetected.get("selected_path", autodetected.get("path"))
    autodetected_status = autodetected.get("status", "unsupported")
    if autodetected_status == "ok" and autodetected_path:
        return {
            "path": autodetected_path,
            "status": "ok",
            "source": "auto_detected",
            "reason": autodetected.get("reason", "auto-detected default path"),
        }

    if configured["status"] in {"missing", "invalid"}:
        return {
            "path": configured["path"],
            "status": configured["status"],
            "source": "configured",
            "reason": configured["reason"],
        }

    return {
        "path": None,
        "status": autodetected_status,
        "source": "auto_detected",
        "reason": autodetected.get("reason", "no path available"),
    }


def _legacy_path_summary(configured: dict[str, object], autodetected: dict[str, object], effective: dict[str, object]) -> dict[str, object]:
    return {
        "configured": configured.get("path"),
        "configured_status": configured.get("status"),
        "auto_detected": autodetected.get("selected_path", autodetected.get("path")),
        "auto_detected_status": autodetected.get("status"),
        "effective": effective.get("path"),
        "effective_status": effective.get("status"),
    }


def run_diagnostics(config: AppConfig, options: DiagnosticsOptions) -> dict[str, object]:
    game_paths = build_game_paths(config.runtime.platform)
    configured_journal_dir = config.paths.journal_dir
    configured_bindings_file = config.paths.bindings_file
    journal_configured = _configured_path_report(configured_journal_dir, kind="journal directory")
    journal_autodetected = _autodetected_path_report(game_paths, kind="journal")
    journal_effective = _effective_path_report(journal_configured, journal_autodetected)
    bindings_configured = _configured_path_report(configured_bindings_file, kind="bindings file")
    bindings_autodetected = _autodetected_path_report(game_paths, kind="bindings")
    bindings_effective = _effective_path_report(bindings_configured, bindings_autodetected)

    effective_journal_dir = Path(journal_effective["path"]) if journal_effective["path"] else None
    effective_bindings_file = Path(bindings_effective["path"]) if bindings_effective["path"] else None

    result: dict[str, object] = {
        "platform": config.runtime.platform,
        "debug": config.runtime.debug,
        "controls": {
            "start_hotkey": config.controls.start_hotkey,
            "stop_hotkey": config.controls.stop_hotkey,
            "scanner_mode": config.controls.scanner_mode,
        },
        "paths": {
            "journal": {
                "configured": journal_configured,
                "auto_detected": journal_autodetected,
                "effective": journal_effective,
            },
            "bindings": {
                "configured": bindings_configured,
                "auto_detected": bindings_autodetected,
                "effective": bindings_effective,
            },
            "legacy_summary": {
                "journal": _legacy_path_summary(journal_configured, journal_autodetected, journal_effective),
                "bindings": _legacy_path_summary(bindings_configured, bindings_autodetected, bindings_effective),
            },
        },
        "options": asdict(options),
        "capture_layout": build_capture_layout(config.screen).to_dict(),
    }

    if effective_journal_dir and effective_journal_dir.exists():
        latest_log = get_latest_journal_log(effective_journal_dir)
        result["latest_log"] = str(latest_log) if latest_log else None
        if latest_log:
            ship_state = read_ship_state(latest_log)
            result["ship_state"] = ship_state.to_dict()

    if effective_bindings_file and effective_bindings_file.exists():
        try:
            bindings, missing = read_bindings(effective_bindings_file)
        except Exception as exc:
            result["bindings_result"] = {
                "status": "error",
                "path": str(effective_bindings_file),
                "error": str(exc),
            }
        else:
            result["bindings_result"] = {
                "status": "ok",
                "path": str(effective_bindings_file),
                "resolved_count": len(bindings),
                "missing_count": len(missing),
            }
            result["bindings"] = {name: binding.to_dict() for name, binding in sorted(bindings.items())}
            result["missing_bindings"] = missing
    else:
        result["bindings_result"] = {
            "status": "not_available",
            "path": str(effective_bindings_file) if effective_bindings_file else None,
            "reason": bindings_effective["reason"],
        }

    if options.capture_screen:
        result["screen_capture"] = run_screen_capture_diagnostic(config)

    if options.send_test_key:
        result["input_test"] = run_input_diagnostic(config, options)

    return result


def run_screen_capture_diagnostic(config: AppConfig) -> dict[str, object]:
    screen_capture = build_screen_capture(config.runtime.platform)
    if screen_capture is None:
        return {"status": "unsupported"}

    capture_layout = build_capture_layout(config.screen)
    base_bounds = capture_layout.base_bounds
    image = screen_capture.capture_region(
        base_bounds.left,
        base_bounds.top,
        base_bounds.right,
        base_bounds.bottom,
    )

    output_path = config.screen.capture_debug_path
    saved_path = None
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
        saved_path = str(output_path)

    return {
        "status": "ok",
        "mode": capture_layout.mode,
        "reference_width": capture_layout.reference_width,
        "reference_height": capture_layout.reference_height,
        "captured_bounds": base_bounds.to_dict(),
        "width": getattr(image, "width", base_bounds.width),
        "height": getattr(image, "height", base_bounds.height),
        "saved_path": saved_path,
    }


def run_input_diagnostic(config: AppConfig, options: DiagnosticsOptions) -> dict[str, object]:
    try:
        input_controller = build_input_controller(config.runtime.platform)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    if input_controller is None:
        return {"status": "unsupported"}

    try:
        if options.delay_s > 0:
            sleep(options.delay_s)
        for _ in range(max(1, options.repeat)):
            input_controller.tap_key(
                options.test_key,
                modifier=options.test_modifier,
                hold_s=options.hold_s,
            )
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    return {
        "status": "ok",
        "test_key": options.test_key,
        "test_modifier": options.test_modifier,
        "hold_s": options.hold_s,
        "delay_s": options.delay_s,
        "repeat": options.repeat,
    }
