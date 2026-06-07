from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from json import loads
from pathlib import Path
from time import sleep
from typing import Callable, Iterator


@dataclass(frozen=True)
class ShipState:
    time_since_log_update_s: int
    status: str | None
    ship_type: str | None
    location: str | None
    star_class: str | None
    target: str | None
    fuel_capacity: float | None
    fuel_level: float | None
    fuel_percent: int
    is_scooping: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class JournalWatcher:
    def __init__(
        self,
        journal_dir: Path,
        *,
        initial_offset: int | None = None,
        poll_interval_s: float = 0.5,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if poll_interval_s < 0:
            raise ValueError("poll_interval_s must be non-negative")
        if initial_offset is not None and initial_offset < 0:
            raise ValueError("initial_offset must be non-negative")

        self._journal_dir = journal_dir
        self._initial_offset = initial_offset
        self._poll_interval_s = poll_interval_s
        self._sleeper = sleeper
        self._current_path: Path | None = None
        self._offset: int | None = None

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    @property
    def offset(self) -> int | None:
        return self._offset

    def poll(self) -> list[dict[str, object]]:
        log_path = get_latest_journal_log(self._journal_dir)
        if log_path is None:
            self._sleep()
            return []

        self._sync_log_path(log_path)
        if self._offset is None:
            self._offset = 0

        file_size = log_path.stat().st_size
        if self._offset > file_size:
            self._offset = 0

        events: list[dict[str, object]] = []
        with log_path.open(encoding="utf-8") as handle:
            handle.seek(self._offset)
            for line in handle:
                stripped = line.strip()
                if stripped:
                    events.append(loads(stripped))
            self._offset = handle.tell()

        if not events:
            self._sleep()
        return events

    def watch(self) -> Iterator[dict[str, object]]:
        while True:
            for event in self.poll():
                yield event

    def _sync_log_path(self, log_path: Path) -> None:
        if log_path == self._current_path:
            return

        self._current_path = log_path
        if self._offset is None:
            self._offset = log_path.stat().st_size if self._initial_offset is None else self._initial_offset
            return

        self._offset = 0

    def _sleep(self) -> None:
        if self._poll_interval_s > 0:
            self._sleeper(self._poll_interval_s)


def get_latest_journal_log(journal_dir: Path) -> Path | None:
    logs = sorted(journal_dir.glob("Journal.*"), key=lambda item: item.stat().st_mtime)
    if not logs:
        return None
    return logs[-1]


def read_ship_state(log_path: Path) -> ShipState:
    last_modified = datetime.fromtimestamp(log_path.stat().st_mtime)
    ship = {
        "time_since_log_update_s": int((datetime.now() - last_modified).total_seconds()),
        "status": None,
        "ship_type": None,
        "location": None,
        "star_class": None,
        "target": None,
        "fuel_capacity": None,
        "fuel_level": None,
        "fuel_percent": 10,
        "is_scooping": False,
    }

    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            log = loads(line)
            event = log.get("event")

            if event == "StartJump":
                ship["status"] = f"starting_{log['JumpType']}".lower()
                if log["JumpType"] == "Hyperspace":
                    ship["star_class"] = log.get("StarClass")
            elif event in {"SupercruiseEntry", "FSDJump"}:
                ship["status"] = "in_supercruise"
            elif (
                event in {"SupercruiseExit", "DockingCancelled"}
                or (
                    event == "Music"
                    and log.get("MusicTrack") == "NoTrack"
                    and ship["status"] == "in_undocking"
                )
                or (event in {"Location", "CarrierJump"} and log.get("Docked") is False)
            ):
                ship["status"] = "in_space"
            elif event == "Undocked":
                if ship["status"] in {"in_station", "starting_undocking", "in_undocking"}:
                    ship["status"] = "in_undocking"
                else:
                    ship["status"] = "in_space"
            elif event == "DockingRequested":
                ship["status"] = "starting_docking"
            elif event == "Music" and log.get("MusicTrack") == "DockingComputer":
                if ship["status"] in {"in_station", "starting_undocking", "in_undocking"}:
                    ship["status"] = "in_undocking"
                elif ship["status"] == "starting_docking":
                    ship["status"] = "in_docking"
            elif event == "Docked" or (
                event in {"Location", "CarrierJump"} and log.get("Docked") is True
            ):
                ship["status"] = "in_station"

            if event in {"LoadGame", "Loadout"}:
                ship["ship_type"] = log.get("Ship")

            if "FuelLevel" in log and ship["ship_type"] != "TestBuggy":
                ship["fuel_level"] = log["FuelLevel"]
            if "FuelCapacity" in log and ship["ship_type"] != "TestBuggy":
                fuel_capacity = log["FuelCapacity"]
                if isinstance(fuel_capacity, dict):
                    ship["fuel_capacity"] = fuel_capacity.get("Main")
                else:
                    ship["fuel_capacity"] = fuel_capacity
            if event == "FuelScoop" and "Total" in log:
                ship["fuel_level"] = log["Total"]
            if ship["fuel_level"] and ship["fuel_capacity"]:
                ship["fuel_percent"] = round((ship["fuel_level"] / ship["fuel_capacity"]) * 100)
            else:
                ship["fuel_percent"] = 10

            ship["is_scooping"] = bool(
                event == "FuelScoop"
                and ship["time_since_log_update_s"] < 10
                and ship["fuel_percent"] < 100
            )

            if event in {"Location", "FSDJump"} and "StarSystem" in log:
                ship["location"] = log["StarSystem"]

            if event == "FSDTarget":
                if log.get("Name") == ship["location"]:
                    ship["target"] = None
                else:
                    ship["target"] = log.get("Name")
            elif event == "FSDJump" and ship["location"] == ship["target"]:
                ship["target"] = None

    return ShipState(**ship)
