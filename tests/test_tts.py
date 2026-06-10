from __future__ import annotations

from threading import Event
import unittest

from edap.config import TTSConfig
from edap.tts import AnnouncementId, QueuedSpeaker, TTSAnnouncer, format_credits_short, normalize_tts_value


class _FakeBackend:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


class _BlockingBackend:
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.started = Event()
        self.release = Event()

    def speak(self, text: str) -> None:
        self.spoken.append(text)
        if len(self.spoken) == 1:
            self.started.set()
            self.release.wait(timeout=1.0)


class TTSHelpersTests(unittest.TestCase):
    def test_queued_speaker_coalesces_stale_pending_items_with_same_key(self) -> None:
        backend = _BlockingBackend()
        speaker = QueuedSpeaker(backend, max_backlog=4)
        self.addCleanup(speaker.close)

        speaker.enqueue("First item")
        self.assertTrue(backend.started.wait(timeout=1.0))

        speaker.enqueue("Route update one", collapse_key=AnnouncementId.DESTINATION_SET)
        speaker.enqueue("Route update two", collapse_key=AnnouncementId.DESTINATION_SET)
        speaker.enqueue("Route update three", collapse_key=AnnouncementId.DESTINATION_SET)

        backend.release.set()
        speaker.close()

        self.assertEqual(backend.spoken, ["First item", "Route update three"])

    def test_queued_speaker_drops_oldest_pending_items_when_backlog_is_full(self) -> None:
        backend = _BlockingBackend()
        speaker = QueuedSpeaker(backend, max_backlog=2)
        self.addCleanup(speaker.close)

        speaker.enqueue("First item")
        self.assertTrue(backend.started.wait(timeout=1.0))

        speaker.enqueue("Second item")
        speaker.enqueue("Third item")
        speaker.enqueue("Fourth item")

        backend.release.set()
        speaker.close()

        self.assertEqual(backend.spoken, ["First item", "Third item", "Fourth item"])

    def test_format_credits_short_humanizes_thousands_and_millions(self) -> None:
        self.assertEqual(format_credits_short(84_200), "84 thousand credits")
        self.assertEqual(format_credits_short(1_250_000), "1.2 million credits")

    def test_normalize_tts_value_spells_three_plus_digits_in_system_and_station_names(self) -> None:
        self.assertEqual(normalize_tts_value("system_name", "HIP 58412"), "HIP 5 8 4 1 2")
        self.assertEqual(normalize_tts_value("station_name", "Pier 2064"), "Pier 2 0 6 4")
        self.assertEqual(normalize_tts_value("system_name", "B13-2"), "B13-2")
        self.assertEqual(normalize_tts_value("system_name", "B100 32-1"), "B1 0 0 32-1")
        self.assertEqual(normalize_tts_value("commodity_name", "Aluminium 2064"), "Aluminium 2064")

    def test_announcer_uses_enum_and_respects_disabled_messages(self) -> None:
        backend = _FakeBackend()
        announcer = TTSAnnouncer(
            TTSConfig(
                enabled=True,
                title_mode="custom",
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
                title_mode="custom",
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

    def test_announcer_spells_long_digits_in_system_names(self) -> None:
        backend = _FakeBackend()
        announcer = TTSAnnouncer(
            TTSConfig(
                enabled=True,
                title_mode="custom",
                title="captain",
                disabled_messages=(),
                phrases={
                    "destination_set": "Setting destination to {system_name}.",
                },
            ),
            platform_name="macos",
            backend=backend,
        )
        self.addCleanup(announcer.close)

        announcer.announce(AnnouncementId.DESTINATION_SET, system_name="HIP 58412")
        announcer.close()

        self.assertEqual(backend.spoken, ["Setting destination to HIP 5 8 4 1 2."])

    def test_announcer_renders_ship_serviced_phrase_with_title(self) -> None:
        backend = _FakeBackend()
        announcer = TTSAnnouncer(
            TTSConfig(
                enabled=True,
                title_mode="custom",
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

    def test_announcer_renders_auto_docking_phrase(self) -> None:
        backend = _FakeBackend()
        announcer = TTSAnnouncer(
            TTSConfig(
                enabled=True,
                title_mode="custom",
                title="captain",
                disabled_messages=(),
                phrases={
                    "auto_docking_engaged": "Engaging auto docking sequence.",
                },
            ),
            platform_name="macos",
            backend=backend,
        )
        self.addCleanup(announcer.close)

        announcer.announce(AnnouncementId.AUTO_DOCKING_ENGAGED)
        announcer.close()

        self.assertEqual(backend.spoken, ["Engaging auto docking sequence."])

    def test_announcer_uses_literal_commander_title_mode(self) -> None:
        backend = _FakeBackend()
        announcer = TTSAnnouncer(
            TTSConfig(
                enabled=True,
                title_mode="commander",
                title="captain",
                disabled_messages=(),
                phrases={
                    "station_cleared": "Ready to jump, {title}.",
                },
            ),
            platform_name="macos",
            backend=backend,
        )
        self.addCleanup(announcer.close)

        announcer.set_commander_name("VRYAE")
        announcer.announce(AnnouncementId.STATION_CLEARED)
        announcer.close()

        self.assertEqual(backend.spoken, ["Ready to jump, commander."])

    def test_announcer_uses_detected_commander_name_title_mode(self) -> None:
        backend = _FakeBackend()
        announcer = TTSAnnouncer(
            TTSConfig(
                enabled=True,
                title_mode="commander_name",
                title="captain",
                disabled_messages=(),
                phrases={
                    "station_cleared": "Ready to jump, {title}.",
                },
            ),
            platform_name="macos",
            backend=backend,
        )
        self.addCleanup(announcer.close)

        announcer.announce(AnnouncementId.STATION_CLEARED)
        announcer.set_commander_name("VRYAE")
        announcer.announce(AnnouncementId.STATION_CLEARED)
        announcer.close()

        self.assertEqual(
            backend.spoken,
            ["Ready to jump, commander.", "Ready to jump, VRYAE."],
        )

    def test_announcer_coalesces_stale_destination_updates(self) -> None:
        backend = _BlockingBackend()
        announcer = TTSAnnouncer(
            TTSConfig(
                enabled=True,
                title_mode="custom",
                title="captain",
                disabled_messages=(),
                phrases={
                    "station_cleared": "Ready to jump, {title}.",
                    "destination_set": "Setting destination to {system_name}.",
                },
            ),
            platform_name="macos",
            backend=backend,
        )
        self.addCleanup(announcer.close)

        announcer.announce(AnnouncementId.STATION_CLEARED)
        self.assertTrue(backend.started.wait(timeout=1.0))

        announcer.announce(AnnouncementId.DESTINATION_SET, system_name="Achenar")
        announcer.announce(AnnouncementId.DESTINATION_SET, system_name="Alioth")
        announcer.announce(AnnouncementId.DESTINATION_SET, system_name="HIP 58412")

        backend.release.set()
        announcer.close()

        self.assertEqual(
            backend.spoken,
            ["Ready to jump, captain.", "Setting destination to HIP 5 8 4 1 2."],
        )
