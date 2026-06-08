from __future__ import annotations

import unittest

from edap.config import TTSConfig
from edap.tts import AnnouncementId, TTSAnnouncer, format_credits_short


class _FakeBackend:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


class TTSHelpersTests(unittest.TestCase):
    def test_format_credits_short_humanizes_thousands_and_millions(self) -> None:
        self.assertEqual(format_credits_short(84_200), "84 thousand credits")
        self.assertEqual(format_credits_short(1_250_000), "1.2 million credits")

    def test_announcer_uses_enum_and_respects_disabled_messages(self) -> None:
        backend = _FakeBackend()
        announcer = TTSAnnouncer(
            TTSConfig(
                enabled=True,
                title="captain",
                disabled_messages=("arrival",),
                phrases={
                    "arrival": "Arrived in {system_name}.",
                    "station_cleared": "Ready to jump, {title}.",
                },
            ),
            platform_name="macos",
            backend=backend,
        )
        self.addCleanup(announcer.close)

        announcer.announce(AnnouncementId.ARRIVAL, system_name="Achenar")
        announcer.announce(AnnouncementId.STATION_CLEARED)
        announcer.close()

        self.assertEqual(backend.spoken, ["Ready to jump, captain."])
