from __future__ import annotations

import re

from edap.routines import RoutineResult


_STATION_MISMATCH_RE = re.compile(
    r"Market\.json is from (?P<market>.+?) but last Docked event is (?P<docked>.+)"
)
_ROUTE_MISMATCH_RE = re.compile(
    r"route mismatch: expected (?P<expected>.+?), got (?P<actual>.+)"
)
_MARKET_NOT_FOUND_RE = re.compile(r"'(?P<target>.+)' not found in market list")


def describe_routine_failure(result: RoutineResult) -> tuple[str, str | None]:
    reason = (result.dispatch.reason or result.dispatch.status or "unknown error").strip()

    station_message = _describe_station_mismatch(reason)
    if station_message is not None:
        return station_message

    route_message = _describe_route_mismatch(reason)
    if route_message is not None:
        return route_message

    market_message = _describe_market_target_mismatch(reason)
    if market_message is not None:
        return market_message

    if "no docked station state found in journal" in reason:
        return (
            "Couldn't confirm your current docked station from the journal yet.",
            "Wait until Elite has fully written the Docked state, then retry.",
        )

    if reason == "Market.json not found":
        return (
            "Couldn't read the station market screen yet.",
            "Open the commodities market fully, wait a moment, then retry.",
        )

    if reason.startswith("sell requires an in-station start"):
        return (
            "Sell can only start while you are docked in station.",
            "Dock first, then rerun the sell step.",
        )

    return (_clean_reason(reason), None)


def _describe_station_mismatch(reason: str) -> tuple[str, str] | None:
    match = _STATION_MISMATCH_RE.search(reason)
    if match is None:
        return None
    market_station = _strip_quotes(match.group("market"))
    docked_station = _strip_quotes(match.group("docked"))
    return (
        f"Station mismatch: market data indicates {market_station}, but we are docked at {docked_station}.",
        "Open replay history with Ctrl-R, press e to edit the station name, then rerun. If this is a different route, start a new haul with the correct station parameters.",
    )


def _describe_route_mismatch(reason: str) -> tuple[str, str] | None:
    match = _ROUTE_MISMATCH_RE.search(reason)
    if match is None:
        return None
    expected = _strip_quotes(match.group("expected"))
    actual = _strip_quotes(match.group("actual"))
    return (
        f"Destination mismatch: expected a route to {expected}, but Elite plotted {actual}.",
        "Use Ctrl-R then e to edit the destination or haul parameters, or start a new haul with the correct route.",
    )


def _describe_market_target_mismatch(reason: str) -> tuple[str, str] | None:
    match = _MARKET_NOT_FOUND_RE.search(reason)
    if match is None:
        return None
    target = match.group("target")
    return (
        f"Commodity mismatch: {target} was not found in this station's market list.",
        "Check the commodity name and station, then use Ctrl-R and e to edit the saved command or start a new haul with the correct parameters.",
    )


def _clean_reason(reason: str) -> str:
    return reason[:1].upper() + reason[1:] if reason else "Unknown error"


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
