from __future__ import annotations

from typing import Any

from edap.control_room.models import ShipState


def apply_ship_event(ship: ShipState, ev: dict[str, Any]) -> None:
    event = ev.get("event", "")

    if event == "Commander":
        ship.commander = ev.get("Name", ship.commander)
    elif event == "LoadGame":
        ship.commander = ev.get("Commander", ship.commander)
        ship.ship_type = ev.get("Ship", ship.ship_type)
        if "Credits" in ev:
            ship.credits = ev["Credits"]
    elif event == "Loadout":
        ship.ship_type = ev.get("Ship", ship.ship_type)
        ship.cargo_capacity = ev.get("CargoCapacity", ship.cargo_capacity)

    if event in {"Location", "FSDJump"} and "StarSystem" in ev:
        ship.system = ev["StarSystem"]
    if event == "Docked" or (
        event in {"Location", "CarrierJump"} and ev.get("Docked") is True
    ):
        ship.station = ev.get("StationName", ship.station)
        ship.system = ev.get("StarSystem", ship.system)
    if event == "SupercruiseExit" or (
        event == "Music"
        and ev.get("MusicTrack") == "NoTrack"
        and ship.status == "in_undocking"
    ) or (
        event in {"Location", "CarrierJump"} and ev.get("Docked") is False
    ):
        ship.station = None

    if event == "StartJump":
        ship.status = f"starting_{ev.get('JumpType', '').lower()}"
    elif event in {"SupercruiseEntry", "FSDJump"}:
        ship.status = "in_supercruise"
    elif event in {"SupercruiseExit", "DockingCancelled"} or (
        event == "Music"
        and ev.get("MusicTrack") == "NoTrack"
        and ship.status == "in_undocking"
    ) or (
        event in {"Location", "CarrierJump"} and ev.get("Docked") is False
    ):
        ship.status = "in_space"
    elif event == "Undocked":
        if ship.status in {"in_station", "starting_undocking", "in_undocking"}:
            ship.status = "in_undocking"
        else:
            ship.status = "in_space"
    elif event == "DockingRequested":
        ship.status = "starting_docking"
    elif event == "Music" and ev.get("MusicTrack") == "DockingComputer":
        if ship.status in {"in_station", "starting_undocking", "in_undocking"}:
            ship.status = "in_undocking"
        elif ship.status == "starting_docking":
            ship.status = "in_docking"
    elif event == "Docked" or (
        event in {"Location", "CarrierJump"} and ev.get("Docked") is True
    ):
        ship.status = "in_station"

    if "FuelLevel" in ev and ship.ship_type != "TestBuggy":
        ship.fuel_level = ev["FuelLevel"]
    if "FuelCapacity" in ev and ship.ship_type != "TestBuggy":
        fuel_capacity = ev["FuelCapacity"]
        ship.fuel_capacity = fuel_capacity.get("Main") if isinstance(fuel_capacity, dict) else fuel_capacity
    if event == "FuelScoop" and "Total" in ev:
        ship.fuel_level = ev["Total"]

    if event == "MarketBuy" and ship.credits is not None and "TotalCost" in ev:
        ship.credits -= ev["TotalCost"]
    elif event == "MarketSell" and ship.credits is not None and "TotalSale" in ev:
        ship.credits += ev["TotalSale"]
    elif "Credits" in ev and event not in {"MarketBuy", "MarketSell"}:
        ship.credits = ev["Credits"]

    if event == "Cargo" and "Count" in ev:
        ship.cargo_count = ev["Count"]
        if "Inventory" in ev:
            ship.cargo_inventory = list(ev["Inventory"])
    elif event == "MarketBuy" and "Count" in ev:
        ship.cargo_count += ev["Count"]
    elif event == "MarketSell" and "Count" in ev:
        ship.cargo_count = max(0, ship.cargo_count - ev["Count"])

    if event == "FSDTarget":
        ship.target = ev.get("Name") if ev.get("Name") != ship.system else None
    elif event == "FSDJump" and ship.system == ship.target:
        ship.target = None
