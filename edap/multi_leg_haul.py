from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen


EXTERNAL_SCHEMA = "edcontrolroom.multi_leg_haul"
EXTERNAL_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CargoTransfer:
    commodity: str
    amount: int
    buy_price: int | None = None
    sell_price: int | None = None
    profit_per_unit: int | None = None
    total_profit: int | None = None


@dataclass(frozen=True)
class RouteEndpoint:
    system: str
    station: str
    distance_to_arrival_ls: int | None = None
    market_id: int | None = None
    market_updated_at: int | None = None
    system_id64: int | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None

    @property
    def label(self) -> str:
        if self.station and self.system:
            return f"{self.station} / {self.system}"
        return self.station or self.system or "unknown stop"


@dataclass(frozen=True)
class RouteLeg:
    index: int
    source: RouteEndpoint
    destination: RouteEndpoint
    cargo: tuple[CargoTransfer, ...]
    jump_distance_ly: float | None = None
    total_profit: int | None = None
    cumulative_profit: int | None = None

    @property
    def cargo_manifest(self) -> str:
        return ", ".join(f"{item.amount}t {item.commodity}" for item in self.cargo) or "no cargo"


@dataclass(frozen=True)
class MultiLegHaulDefinition:
    route_name: str
    legs: tuple[RouteLeg, ...]
    source_provider: str | None = None
    source_job: str | None = None
    source_url: str | None = None
    source_parameters: dict[str, Any] | None = None

    @property
    def total_legs(self) -> int:
        return len(self.legs)


@dataclass(frozen=True)
class RouteStop:
    index: int
    endpoint: RouteEndpoint
    inbound: tuple[CargoTransfer, ...]
    outbound: tuple[CargoTransfer, ...]
    next_system: str | None

    @property
    def label(self) -> str:
        return f"stop {self.index + 1} ({self.endpoint.label})"


def load_multi_leg_haul_definition(source: str | Path) -> MultiLegHaulDefinition:
    if isinstance(source, Path):
        payload = json.loads(source.read_text(encoding="utf-8"))
        return multi_leg_haul_definition_from_data(payload, source_label=str(source))

    text = str(source).strip()
    if not text:
        raise ValueError("multi-leg haul source is required")
    if _looks_like_url(text):
        with urlopen(text) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        return multi_leg_haul_definition_from_data(payload, source_label=text)
    path = Path(text)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return multi_leg_haul_definition_from_data(payload, source_label=str(path))
    if text.startswith("{"):
        return multi_leg_haul_definition_from_data(json.loads(text), source_label="inline json")
    raise FileNotFoundError(f"Route source not found: {text}")


def multi_leg_haul_definition_from_data(
    data: Any,
    *,
    source_label: str | None = None,
) -> MultiLegHaulDefinition:
    if not isinstance(data, dict):
        raise ValueError("multi-leg haul definition must be a JSON object")
    schema = data.get("schema")
    if schema == EXTERNAL_SCHEMA:
        return _definition_from_external_json(data)
    if {"job", "result", "state", "status"} <= set(data.keys()):
        return _definition_from_spansh(data, source_label=source_label)
    raise ValueError("Unsupported multi-leg haul payload")


def multi_leg_haul_definition_to_external_json(definition: MultiLegHaulDefinition) -> dict[str, Any]:
    return {
        "schema": EXTERNAL_SCHEMA,
        "version": EXTERNAL_SCHEMA_VERSION,
        "route_name": definition.route_name,
        "source": {
            "provider": definition.source_provider,
            "job": definition.source_job,
            "url": definition.source_url,
            "parameters": definition.source_parameters or {},
        },
        "legs": [
            {
                "index": leg.index,
                "source": _endpoint_to_json(leg.source),
                "destination": _endpoint_to_json(leg.destination),
                "distance_ly": leg.jump_distance_ly,
                "total_profit": leg.total_profit,
                "cumulative_profit": leg.cumulative_profit,
                "cargo": [
                    {
                        "commodity": item.commodity,
                        "amount": item.amount,
                        "buy_price": item.buy_price,
                        "sell_price": item.sell_price,
                        "profit_per_unit": item.profit_per_unit,
                        "total_profit": item.total_profit,
                    }
                    for item in leg.cargo
                ],
            }
            for leg in definition.legs
        ],
    }


def build_route_stops(definition: MultiLegHaulDefinition) -> tuple[RouteStop, ...]:
    if not definition.legs:
        return ()
    stops: list[RouteStop] = []
    first_leg = definition.legs[0]
    stops.append(
        RouteStop(
            index=0,
            endpoint=first_leg.source,
            inbound=(),
            outbound=first_leg.cargo,
            next_system=first_leg.destination.system or None,
        )
    )
    for index, leg in enumerate(definition.legs, start=1):
        next_leg = definition.legs[index] if index < len(definition.legs) else None
        stops.append(
            RouteStop(
                index=index,
                endpoint=leg.destination,
                inbound=leg.cargo,
                outbound=next_leg.cargo if next_leg is not None else (),
                next_system=next_leg.destination.system if next_leg is not None else None,
            )
        )
    return tuple(stops)


def _definition_from_external_json(data: dict[str, Any]) -> MultiLegHaulDefinition:
    version = data.get("version")
    if version != EXTERNAL_SCHEMA_VERSION:
        raise ValueError(f"Unsupported multi-leg haul schema version: {version!r}")
    route_name = str(data.get("route_name", "")).strip()
    if not route_name:
        raise ValueError("route_name is required")
    raw_source = data.get("source", {})
    if not isinstance(raw_source, dict):
        raw_source = {}
    raw_legs = data.get("legs", [])
    if not isinstance(raw_legs, list) or not raw_legs:
        raise ValueError("At least one leg is required")
    legs = tuple(_leg_from_external_json(item, index) for index, item in enumerate(raw_legs, start=1))
    return MultiLegHaulDefinition(
        route_name=route_name,
        legs=legs,
        source_provider=_string_or_none(raw_source.get("provider")),
        source_job=_string_or_none(raw_source.get("job")),
        source_url=_string_or_none(raw_source.get("url")),
        source_parameters=raw_source.get("parameters") if isinstance(raw_source.get("parameters"), dict) else {},
    )


def _definition_from_spansh(
    data: dict[str, Any],
    *,
    source_label: str | None,
) -> MultiLegHaulDefinition:
    status = str(data.get("status", ""))
    state = str(data.get("state", ""))
    if status.lower() != "ok" or state.lower() != "completed":
        raise ValueError(f"Spansh route is not complete: status={status!r} state={state!r}")
    raw_legs = data.get("result", [])
    if not isinstance(raw_legs, list) or not raw_legs:
        raise ValueError("Spansh route result is empty")
    legs = tuple(_leg_from_spansh(item, index) for index, item in enumerate(raw_legs, start=1))
    route_name = _build_spansh_route_name(legs)
    return MultiLegHaulDefinition(
        route_name=route_name,
        legs=legs,
        source_provider="spansh",
        source_job=_string_or_none(data.get("job")),
        source_url=source_label,
        source_parameters=data.get("parameters") if isinstance(data.get("parameters"), dict) else {},
    )


def _leg_from_external_json(data: Any, index: int) -> RouteLeg:
    if not isinstance(data, dict):
        raise ValueError(f"Leg {index} must be an object")
    cargo = data.get("cargo", [])
    if not isinstance(cargo, list) or not cargo:
        raise ValueError(f"Leg {index} cargo is required")
    return RouteLeg(
        index=index,
        source=_endpoint_from_json(data.get("source"), label=f"leg {index} source"),
        destination=_endpoint_from_json(data.get("destination"), label=f"leg {index} destination"),
        cargo=tuple(_cargo_from_external_json(item, index=index) for item in cargo),
        jump_distance_ly=_float_or_none(data.get("distance_ly")),
        total_profit=_int_or_none(data.get("total_profit")),
        cumulative_profit=_int_or_none(data.get("cumulative_profit")),
    )


def _leg_from_spansh(data: Any, index: int) -> RouteLeg:
    if not isinstance(data, dict):
        raise ValueError(f"Spansh leg {index} must be an object")
    raw_cargo = data.get("commodities", [])
    if not isinstance(raw_cargo, list) or not raw_cargo:
        raise ValueError(f"Spansh leg {index} has no commodities")
    return RouteLeg(
        index=index,
        source=_endpoint_from_json(data.get("source"), label=f"spansh leg {index} source"),
        destination=_endpoint_from_json(data.get("destination"), label=f"spansh leg {index} destination"),
        cargo=tuple(_cargo_from_spansh(item, index=index) for item in raw_cargo),
        jump_distance_ly=_float_or_none(data.get("distance")),
        total_profit=_int_or_none(data.get("total_profit")),
        cumulative_profit=_int_or_none(data.get("cumulative_profit")),
    )


def _endpoint_from_json(data: Any, *, label: str) -> RouteEndpoint:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be an object")
    system = str(data.get("system", "")).strip()
    station = str(data.get("station", "")).strip()
    if not system and not station:
        raise ValueError(f"{label} needs a station or system")
    return RouteEndpoint(
        system=system,
        station=station,
        distance_to_arrival_ls=_int_or_none(data.get("distance_to_arrival")),
        market_id=_int_or_none(data.get("market_id")),
        market_updated_at=_int_or_none(data.get("market_updated_at")),
        system_id64=_int_or_none(data.get("system_id64")),
        x=_float_or_none(data.get("x")),
        y=_float_or_none(data.get("y")),
        z=_float_or_none(data.get("z")),
    )


def _endpoint_to_json(endpoint: RouteEndpoint) -> dict[str, Any]:
    return {
        "system": endpoint.system,
        "station": endpoint.station,
        "distance_to_arrival": endpoint.distance_to_arrival_ls,
        "market_id": endpoint.market_id,
        "market_updated_at": endpoint.market_updated_at,
        "system_id64": endpoint.system_id64,
        "x": endpoint.x,
        "y": endpoint.y,
        "z": endpoint.z,
    }


def _cargo_from_external_json(data: Any, *, index: int) -> CargoTransfer:
    if not isinstance(data, dict):
        raise ValueError(f"Leg {index} cargo item must be an object")
    commodity = str(data.get("commodity", "")).strip()
    amount = _int_or_none(data.get("amount"))
    if not commodity or amount is None or amount <= 0:
        raise ValueError(f"Leg {index} cargo item needs commodity and positive amount")
    return CargoTransfer(
        commodity=commodity,
        amount=amount,
        buy_price=_int_or_none(data.get("buy_price")),
        sell_price=_int_or_none(data.get("sell_price")),
        profit_per_unit=_int_or_none(data.get("profit_per_unit")),
        total_profit=_int_or_none(data.get("total_profit")),
    )


def _cargo_from_spansh(data: Any, *, index: int) -> CargoTransfer:
    if not isinstance(data, dict):
        raise ValueError(f"Spansh leg {index} cargo item must be an object")
    commodity = str(data.get("name", "")).strip()
    amount = _int_or_none(data.get("amount"))
    if not commodity or amount is None or amount <= 0:
        raise ValueError(f"Spansh leg {index} cargo item needs name and amount")
    source_commodity = data.get("source_commodity", {})
    destination_commodity = data.get("destination_commodity", {})
    if not isinstance(source_commodity, dict):
        source_commodity = {}
    if not isinstance(destination_commodity, dict):
        destination_commodity = {}
    return CargoTransfer(
        commodity=commodity,
        amount=amount,
        buy_price=_int_or_none(source_commodity.get("buy_price")),
        sell_price=_int_or_none(destination_commodity.get("sell_price")),
        profit_per_unit=_int_or_none(data.get("profit")),
        total_profit=_int_or_none(data.get("total_profit")),
    )


def _build_spansh_route_name(legs: tuple[RouteLeg, ...]) -> str:
    first = legs[0]
    last = legs[-1]
    return f"{first.source.station} -> {last.destination.station} ({len(legs)} legs)"


def _string_or_none(value: Any) -> str | None:
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(value)
    return None


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return None


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
