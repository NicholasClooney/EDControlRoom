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
                    "arrival": "We are dropping out of hyper space jump captain.",
                    "station_cleared": "Ready to jump, {title}.",
                    "haul_aborted": "Haul aborted.",
                },
            ),
            platform_name="macos",
            backend=backend,
        )
        self.addCleanup(announcer.close)

        announcer.announce(AnnouncementId.ARRIVAL, system_name="Achenar")
        announcer.announce(AnnouncementId.STATION_CLEARED)
        announcer.announce(AnnouncementId.HAUL_ABORTED)
        announcer.close()

        self.assertEqual(backend.spoken, ["Ready to jump, captain.", "Haul aborted."])

    def test_announcer_renders_market_level_low_phrase(self) -> None:
        backend = _FakeBackend()
        announcer = TTSAnnouncer(
            TTSConfig(
                enabled=True,
                title="captain",
                disabled_messages=(),
                phrases={
                    "market_level_low": "Station {market_side} for {commodity_name} is low at {units} units.",
                },
            ),
            platform_name="macos",
            backend=backend,
        )
        self.addCleanup(announcer.close)

        announcer.announce(
            AnnouncementId.MARKET_LEVEL_LOW,
            market_side="demand",
            commodity_name="Aluminium",
            units=200,
        )
        announcer.close()

        self.assertEqual(backend.spoken, ["Station demand for Aluminium is low at 200 units."])

    def test_announcer_renders_ship_serviced_phrase_with_title(self) -> None:
        backend = _FakeBackend()
        announcer = TTSAnnouncer(
            TTSConfig(
                enabled=True,
                title="captain",
                disabled_messages=(),
                phrases={
                    "ship_serviced": "Ship is fully fueled up and repaired, {title}.",
                },
            ),
            platform_name="macos",
            backend=backend,
        )
        self.addCleanup(announcer.close)

        announcer.announce(AnnouncementId.SHIP_SERVICED)
        announcer.close()

        self.assertEqual(backend.spoken, ["Ship is fully fueled up and repaired, captain."])
