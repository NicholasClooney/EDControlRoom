from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from queue import Empty, Queue
from shutil import which
import subprocess
from threading import Thread
from typing import Protocol

from edap.config import TTSConfig


class AnnouncementId(str, Enum):
    DESTINATION_SET = "destination_set"
    STATION_CLEARED = "station_cleared"
    HAUL_ABORTED = "haul_aborted"
    BUYING_CARGO = "buying_cargo"
    SELLING_CARGO = "selling_cargo"
    SALE_PROFIT = "sale_profit"
    JUMP_INITIATED = "jump_initiated"
    ARRIVAL = "arrival"
    APPROACHING_STATION = "approaching_station"
    DOCKING_REQUEST = "docking_request"
    DOCKING_COMPLETE = "docking_complete"
    SHIP_SERVICED = "ship_serviced"
    UNDOCKING = "undocking"
    CARGO_LOADED = "cargo_loaded"
    ROUTE_COMPLETE = "route_complete"
    SESSION_COMPLETE = "session_complete"
    MARKET_LEVEL_LOW = "market_level_low"


def parse_announcement_id(value: str) -> AnnouncementId | None:
    try:
        return AnnouncementId(value)
    except ValueError:
        return None


def format_credits_short(value: int) -> str:
    abs_value = abs(int(value))
    if abs_value >= 1_000_000:
        amount = f"{abs_value / 1_000_000:.1f}".rstrip("0").rstrip(".")
        prefix = "-" if value < 0 else ""
        return f"{prefix}{amount} million credits"
    if abs_value >= 1_000:
        amount = int(round(abs_value / 1_000))
        prefix = "-" if value < 0 else ""
        return f"{prefix}{amount} thousand credits"
    return f"{value} credits"


class SpeechBackend(Protocol):
    def speak(self, text: str) -> None: ...


class NullSpeechBackend:
    def speak(self, text: str) -> None:
        return None


@dataclass(frozen=True)
class CommandSpeechBackend:
    command_prefix: tuple[str, ...]

    def speak(self, text: str) -> None:
        subprocess.run([*self.command_prefix, text], check=False, capture_output=True)


@dataclass(frozen=True)
class PowerShellSpeechBackend:
    executable: str

    def speak(self, text: str) -> None:
        escaped = text.replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$speaker.Speak('{escaped}')"
        )
        subprocess.run(
            [self.executable, "-NoProfile", "-Command", script],
            check=False,
            capture_output=True,
        )


def build_speech_backend(platform_name: str) -> SpeechBackend:
    platform_name = platform_name.lower()
    if platform_name == "macos" and which("say"):
        return CommandSpeechBackend(("say",))
    if platform_name == "linux":
        for name in ("spd-say", "espeak-ng", "espeak"):
            if which(name):
                return CommandSpeechBackend((name,))
    if platform_name == "windows":
        for executable in ("powershell", "pwsh"):
            if which(executable):
                return PowerShellSpeechBackend(executable)
    return NullSpeechBackend()


class QueuedSpeaker:
    def __init__(self, backend: SpeechBackend) -> None:
        self._backend = backend
        self._queue: Queue[str | None] = Queue()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def enqueue(self, text: str) -> None:
        self._queue.put(text)

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while True:
            try:
                text = self._queue.get(timeout=0.1)
            except Empty:
                continue
            if text is None:
                return
            self._backend.speak(text)


class TTSAnnouncer:
    def __init__(
        self,
        config: TTSConfig,
        *,
        platform_name: str,
        backend: SpeechBackend | None = None,
    ) -> None:
        self._config = config
        self._disabled = {
            parsed
            for raw in config.disabled_messages
            if (parsed := parse_announcement_id(raw)) is not None
        }
        self._phrases = {
            parsed: text
            for raw, text in config.phrases.items()
            if (parsed := parse_announcement_id(raw)) is not None
        }
        self._speaker: QueuedSpeaker | None = None
        self._last_text = ""
        selected_backend = backend if backend is not None else build_speech_backend(platform_name)
        if config.enabled and not isinstance(selected_backend, NullSpeechBackend):
            self._speaker = QueuedSpeaker(selected_backend)

    def announce(self, message_id: AnnouncementId, /, **values: object) -> None:
        if self._speaker is None or message_id in self._disabled:
            return
        template = self._phrases.get(message_id)
        if not template:
            return
        rendered = template.format(title=self._config.title, **values).strip()
        if not rendered or rendered == self._last_text:
            return
        self._last_text = rendered
        self._speaker.enqueue(rendered)

    def close(self) -> None:
        if self._speaker is not None:
            self._speaker.close()
            self._speaker = None
