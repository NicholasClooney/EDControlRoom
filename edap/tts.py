from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import re
from shutil import which
import subprocess
from threading import Condition, Thread
from typing import Protocol

from edap.config import TTSConfig


class AnnouncementId(str, Enum):
    DESTINATION_SET = "destination_set"
    STATION_CLEARED = "station_cleared"
    HAUL_ABORTED = "haul_aborted"
    HAUL_STOP_AFTER_RUN = "haul_stop_after_run"
    BUYING_CARGO = "buying_cargo"
    SELLING_CARGO = "selling_cargo"
    SALE_PROFIT = "sale_profit"
    JUMP_INITIATED = "jump_initiated"
    ARRIVAL = "arrival"
    ARRIVAL_NEXT_STATION = "arrival_next_station"
    APPROACHING_STATION = "approaching_station"
    DOCKING_REQUEST = "docking_request"
    AUTO_DOCKING_ENGAGED = "auto_docking_engaged"
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


_DIGIT_RUN_RE = re.compile(r"\d{3,}")
_SPOKEN_NAME_FIELDS = frozenset({"system_name", "station_name"})


def _spell_digit_runs(text: str) -> str:
    return _DIGIT_RUN_RE.sub(lambda match: " ".join(match.group(0)), text)


def normalize_tts_value(field_name: str, value: object) -> object:
    if field_name not in _SPOKEN_NAME_FIELDS or not isinstance(value, str):
        return value
    return _spell_digit_runs(value)


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
    def __init__(self, backend: SpeechBackend, *, max_backlog: int = 8) -> None:
        if max_backlog < 1:
            raise ValueError("QueuedSpeaker max_backlog must be at least 1.")
        self._backend = backend
        self._max_backlog = max_backlog
        self._pending: deque[_SpeechItem] = deque()
        self._condition = Condition()
        self._closed = False
        self._speaking = False
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def enqueue(self, text: str, *, collapse_key: object | None = None) -> None:
        item = _SpeechItem(text=text, collapse_key=collapse_key)
        with self._condition:
            if self._closed:
                return
            if (
                collapse_key is not None
                and self._speaking
                and any(queued.collapse_key == collapse_key for queued in self._pending)
            ):
                self._pending = deque(
                    queued for queued in self._pending if queued.collapse_key != collapse_key
                )
            while len(self._pending) >= self._max_backlog:
                self._pending.popleft()
            self._pending.append(item)
            self._condition.notify()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._pending and not self._closed:
                    self._condition.wait(timeout=0.1)
                if not self._pending and self._closed:
                    return
                item = self._pending.popleft()
                self._speaking = True
            try:
                self._backend.speak(item.text)
            finally:
                with self._condition:
                    self._speaking = False


@dataclass(frozen=True)
class _SpeechItem:
    text: str
    collapse_key: object | None = None


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
        self._commander_name: str | None = None
        self._speaker: QueuedSpeaker | None = None
        self._last_text = ""
        selected_backend = backend if backend is not None else build_speech_backend(platform_name)
        if config.enabled and not isinstance(selected_backend, NullSpeechBackend):
            self._speaker = QueuedSpeaker(selected_backend)

    def set_commander_name(self, name: str | None) -> None:
        text = str(name).strip() if name is not None else ""
        self._commander_name = text or None

    def announce(self, message_id: AnnouncementId, /, **values: object) -> None:
        if self._speaker is None or message_id in self._disabled:
            return
        template = self._phrases.get(message_id)
        if not template:
            return
        normalized_values = {
            key: normalize_tts_value(key, value)
            for key, value in values.items()
        }
        rendered = template.format(title=self._resolve_title(), **normalized_values).strip()
        if not rendered or rendered == self._last_text:
            return
        self._last_text = rendered
        self._speaker.enqueue(rendered, collapse_key=message_id)

    def _resolve_title(self) -> str:
        if self._config.title_mode == "commander":
            return "commander"
        if self._config.title_mode == "commander_name":
            return self._commander_name or "commander"
        return self._config.title

    def close(self) -> None:
        if self._speaker is not None:
            self._speaker.close()
            self._speaker = None
