from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from edap import version


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self, *_args, **_kwargs) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class VersionTests(unittest.TestCase):
    def test_display_version_adds_v_prefix(self) -> None:
        self.assertEqual(version.display_version("1.7.1"), "v1.7.1")
        self.assertEqual(version.display_version("v1.7.1"), "v1.7.1")

    def test_is_newer_version_compares_semver_like_tags(self) -> None:
        self.assertTrue(version.is_newer_version("v1.8.0", "1.7.1"))
        self.assertTrue(version.is_newer_version("1.7.1.1", "1.7.1"))
        self.assertFalse(version.is_newer_version("1.7.1", "1.7.1"))
        self.assertFalse(version.is_newer_version("1.7.0", "1.7.1"))

    def test_fetch_latest_github_release_parses_response(self) -> None:
        payload = {
            "tag_name": "v1.8.0",
            "name": "EDAutoPilot Mk II v1.8.0 - Test",
            "html_url": "https://github.com/NicholasClooney/EDAutoPilotMKII/releases/tag/v1.8.0",
            "published_at": "2026-06-10T00:00:00Z",
        }

        with patch("edap.version.urlopen", return_value=_FakeResponse(payload)):
            release = version.fetch_latest_github_release()

        self.assertIsNotNone(release)
        assert release is not None
        self.assertEqual(release.tag_name, "v1.8.0")
        self.assertEqual(release.version, "1.8.0")

    def test_fetch_latest_github_release_returns_none_for_invalid_payload(self) -> None:
        with patch("edap.version.urlopen", return_value=_FakeResponse({"tag_name": ""})):
            release = version.fetch_latest_github_release()

        self.assertIsNone(release)
