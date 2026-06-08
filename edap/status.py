from __future__ import annotations

from dataclasses import dataclass
from json import loads
from pathlib import Path


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class StatusFlags:
    docked: bool
    landed: bool
    landing_gear_down: bool
    shields_up: bool
    supercruise: bool
    flight_assist_off: bool
    hardpoints_deployed: bool
    in_wing: bool
    lights_on: bool
    cargo_scoop_deployed: bool
    silent_running: bool
    scooping_fuel: bool
    srv_handbrake: bool
    srv_turret_view: bool
    srv_turret_retracted: bool
    srv_drive_assist: bool
    fsd_mass_locked: bool
    fsd_charging: bool
    fsd_cooldown: bool
    low_fuel: bool
    overheating: bool
    has_lat_long: bool
    is_in_danger: bool
    being_interdicted: bool
    in_main_ship: bool
    in_fighter: bool
    in_srv: bool
    hud_analysis_mode: bool
    night_vision: bool
    altitude_from_average_radius: bool
    fsd_jump: bool
    srv_high_beam: bool

    @classmethod
    def from_int(cls, flags: int) -> StatusFlags:
        return cls(
            docked=bool(flags & (1 << 0)),
            landed=bool(flags & (1 << 1)),
            landing_gear_down=bool(flags & (1 << 2)),
            shields_up=bool(flags & (1 << 3)),
            supercruise=bool(flags & (1 << 4)),
            flight_assist_off=bool(flags & (1 << 5)),
            hardpoints_deployed=bool(flags & (1 << 6)),
            in_wing=bool(flags & (1 << 7)),
            lights_on=bool(flags & (1 << 8)),
            cargo_scoop_deployed=bool(flags & (1 << 9)),
            silent_running=bool(flags & (1 << 10)),
            scooping_fuel=bool(flags & (1 << 11)),
            srv_handbrake=bool(flags & (1 << 12)),
            srv_turret_view=bool(flags & (1 << 13)),
            srv_turret_retracted=bool(flags & (1 << 14)),
            srv_drive_assist=bool(flags & (1 << 15)),
            fsd_mass_locked=bool(flags & (1 << 16)),
            fsd_charging=bool(flags & (1 << 17)),
            fsd_cooldown=bool(flags & (1 << 18)),
            low_fuel=bool(flags & (1 << 19)),
            overheating=bool(flags & (1 << 20)),
            has_lat_long=bool(flags & (1 << 21)),
            is_in_danger=bool(flags & (1 << 22)),
            being_interdicted=bool(flags & (1 << 23)),
            in_main_ship=bool(flags & (1 << 24)),
            in_fighter=bool(flags & (1 << 25)),
            in_srv=bool(flags & (1 << 26)),
            hud_analysis_mode=bool(flags & (1 << 27)),
            night_vision=bool(flags & (1 << 28)),
            altitude_from_average_radius=bool(flags & (1 << 29)),
            fsd_jump=bool(flags & (1 << 30)),
            srv_high_beam=bool(flags & (1 << 31)),
        )


@dataclass(frozen=True)
class ShipStatus:
    flags: StatusFlags
    raw_flags: int
    pips_sys: int | None
    pips_eng: int | None
    pips_wep: int | None
    fire_group: int | None
    gui_focus: int | None
    fuel_main: float | None
    fuel_reservoir: float | None
    cargo: float | None
    legal_state: str | None
    balance: int | None
    destination_system: str | None
    destination_body: str | None
    destination_name: str | None


def read_status(journal_dir: Path) -> ShipStatus | None:
    path = journal_dir / "Status.json"
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None

    data = loads(text)
    raw_flags = data.get("Flags", 0)
    pips = data.get("Pips")
    fuel = data.get("Fuel") or {}
    destination = data.get("Destination") or {}

    return ShipStatus(
        flags=StatusFlags.from_int(raw_flags),
        raw_flags=raw_flags,
        pips_sys=pips[0] if pips else None,
        pips_eng=pips[1] if pips else None,
        pips_wep=pips[2] if pips else None,
        fire_group=data.get("FireGroup"),
        gui_focus=data.get("GuiFocus"),
        fuel_main=fuel.get("FuelMain"),
        fuel_reservoir=fuel.get("FuelReservoir"),
        cargo=data.get("Cargo"),
        legal_state=data.get("LegalState"),
        balance=data.get("Balance"),
        destination_system=_optional_text(destination.get("System")),
        destination_body=_optional_text(destination.get("Body")),
        destination_name=_optional_text(destination.get("Name")),
    )
