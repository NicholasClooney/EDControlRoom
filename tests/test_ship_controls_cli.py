from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ship_controls


class _FakeControls:
    def __init__(self, expected_result: dict[str, object]) -> None:
        self.expected_result = expected_result
        self.calls: list[dict[str, object]] = []

    def tap_action(self, action: str, repeat: int = 1, hold_s: float = 0.0):
        self.calls.append({"action": action, "repeat": repeat, "hold_s": hold_s})

        class _Result:
            def __init__(self, payload: dict[str, object]) -> None:
                self.status = payload["status"]
                self._payload = payload

            def to_dict(self) -> dict[str, object]:
                return dict(self._payload)

        return _Result(self.expected_result)


class ShipControlsCliTests(unittest.TestCase):
    def test_resolve_bindings_file_prefers_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bindings_file = Path(temp_dir) / "Custom.binds"
            bindings_file.write_text("<Root />", encoding="utf-8")
            config = ship_controls.load_config("config.example.toml")
            config = config.__class__(
                paths=config.paths.__class__(journal_dir=config.paths.journal_dir, bindings_file=bindings_file),
                controls=config.controls,
                screen=config.screen,
                runtime=config.runtime,
            )

            resolved, source = ship_controls._resolve_bindings_file(config)

            self.assertEqual(resolved, str(bindings_file))
            self.assertEqual(source, "configured")

    def test_main_dispatches_action_and_emits_json(self) -> None:
        fake_controls = _FakeControls({"action": "RollLeftButton", "status": "ok"})

        with patch("ship_controls._load_config_with_fallback") as load_config_mock, patch(
            "ship_controls._resolve_bindings_file",
            return_value=("/tmp/Custom.binds", "auto_detected"),
        ), patch("ship_controls.build_input_controller", return_value=object()), patch(
            "ship_controls.ShipControls.from_bindings_file",
            return_value=fake_controls,
        ), patch("sys.stdout", new_callable=io.StringIO) as stdout, patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            load_config_mock.return_value = (ship_controls.load_config("config.example.toml"), "config.example.toml", True)

            with patch("sys.argv", ["ship_controls.py", "--action", "RollLeftButton", "--repeat", "2", "--hold-seconds", "0.1"]):
                exit_code = ship_controls.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_controls.calls, [{"action": "RollLeftButton", "repeat": 2, "hold_s": 0.1}])
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["bindings_source"], "auto_detected")
        self.assertEqual(payload["result"]["status"], "ok")
        self.assertIn("Sending RollLeftButton 2 times", stderr.getvalue())

    def test_countdown_logs_to_stderr(self) -> None:
        with patch("ship_controls.sleep") as sleep_mock, patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            ship_controls._sleep_with_countdown("RollLeftButton", 2.0)

        self.assertEqual(sleep_mock.call_count, 2)
        self.assertIn("Sending RollLeftButton in 2s", stderr.getvalue())
        self.assertIn("Sending RollLeftButton in 1s", stderr.getvalue())
