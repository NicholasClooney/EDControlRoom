from __future__ import annotations

import re

from edap.config import AppConfig
from edap.control_room import error_text
from edap.routines import RoutineResult


_STATION_MISMATCH_RE = re.compile(
    r"Market\.json is from (?P<market>.+?) but last Docked event is (?P<docked>.+)"
)
_ROUTE_MISMATCH_RE = re.compile(
    r"route mismatch: expected (?P<expected>.+?), got (?P<actual>.+)"
)
_MARKET_NOT_FOUND_RE = re.compile(r"'(?P<target>.+)' not found in market list")
_MARKET_EVENT_TIMEOUT_RE = re.compile(
    r"(?P<event_type>MarketBuy|MarketSell) for '(?P<target>.+)' not observed within (?P<timeout_s>\d+(?:\.\d+)?)s"
)


def describe_routine_failure(
    result: RoutineResult,
    config: AppConfig,
) -> tuple[str, str | None]:
    reason = (result.dispatch.reason or result.dispatch.status or "unknown error").strip()

    station_message = _describe_station_mismatch(reason, config)
    if station_message is not None:
        return station_message

    route_message = _describe_route_mismatch(reason, config)
    if route_message is not None:
        return route_message

    market_message = _describe_market_target_mismatch(reason, config)
    if market_message is not None:
        return market_message

    event_timeout_message = _describe_trade_event_timeout(reason, config)
    if event_timeout_message is not None:
        return event_timeout_message

    if "no docked station state found in journal" in reason:
        return (
            error_text.render(config, "journal_docked_state_missing_message"),
            error_text.render(config, "journal_docked_state_missing_suggestion"),
        )

    if reason == "Market.json not found":
        return (
            error_text.render(config, "market_data_missing_message"),
            error_text.render(config, "market_data_missing_suggestion"),
        )

    if reason.startswith("sell requires an in-station start"):
        return (
            error_text.render(config, "sell_requires_docked_message"),
            error_text.render(config, "sell_requires_docked_suggestion"),
        )

    if reason.startswith("sell return-to-station check failed:"):
        return (
            error_text.render(config, "sell_return_station_check_message"),
            error_text.render(config, "sell_return_station_check_suggestion"),
        )

    if reason == "amount must be at least 1":
        return (error_text.render(config, "amount_minimum_message"), None)

    if reason == "cargo hold empty":
        return (
            error_text.render(config, "cargo_hold_empty_message"),
            error_text.render(config, "cargo_hold_empty_suggestion"),
        )

    if reason == "jump did not reach in_supercruise before retry budget was exhausted":
        return (
            error_text.render(config, "jump_retry_exhausted_message"),
            error_text.render(config, "jump_retry_exhausted_suggestion"),
        )

    if reason == "docked event was not observed before timeout":
        return (
            error_text.render(config, "docked_timeout_message"),
            error_text.render(config, "docked_timeout_suggestion"),
        )

    if reason == "supercruise exit was not observed before timeout":
        return (
            error_text.render(config, "supercruise_exit_timeout_message"),
            error_text.render(config, "supercruise_exit_timeout_suggestion"),
        )

    if reason == "docking request/grant was not observed before retry budget was exhausted":
        return (
            error_text.render(config, "docking_request_timeout_message"),
            error_text.render(config, "docking_request_timeout_suggestion"),
        )

    if reason.startswith("Undocked event was not observed within"):
        return (
            error_text.render(config, "undocked_timeout_message"),
            error_text.render(config, "undocked_timeout_suggestion"),
        )

    if reason.startswith("NoTrack music event was not observed within"):
        return (
            error_text.render(config, "no_track_timeout_message"),
            error_text.render(config, "no_track_timeout_suggestion"),
        )

    return (_clean_reason(reason), None)


def describe_routine_exception(exc: Exception, config: AppConfig) -> tuple[str, str | None]:
    return (
        error_text.render(config, "routine_unexpected_exception", error=str(exc)),
        error_text.render(config, "routine_unexpected_exception_suggestion"),
    )


def _describe_station_mismatch(reason: str, config: AppConfig) -> tuple[str, str] | None:
    match = _STATION_MISMATCH_RE.search(reason)
    if match is None:
        return None
    market_station = _strip_quotes(match.group("market"))
    docked_station = _strip_quotes(match.group("docked"))
    return (
        error_text.render(
            config,
            "station_mismatch_message",
            market_station=market_station,
            docked_station=docked_station,
        ),
        error_text.render(config, "station_mismatch_suggestion"),
    )


def _describe_route_mismatch(reason: str, config: AppConfig) -> tuple[str, str] | None:
    match = _ROUTE_MISMATCH_RE.search(reason)
    if match is None:
        return None
    expected = _strip_quotes(match.group("expected"))
    actual = _strip_quotes(match.group("actual"))
    return (
        error_text.render(
            config,
            "route_mismatch_message",
            expected=expected,
            actual=actual,
        ),
        error_text.render(config, "route_mismatch_suggestion"),
    )


def _describe_market_target_mismatch(reason: str, config: AppConfig) -> tuple[str, str] | None:
    match = _MARKET_NOT_FOUND_RE.search(reason)
    if match is not None:
        target = match.group("target")
        return (
            error_text.render(config, "market_target_not_found_message", target=target),
            error_text.render(config, "market_target_not_found_suggestion"),
        )

    data_match = re.search(r"'(?P<target>.+)' matched navigation list but not market item data", reason)
    if data_match is None:
        return None
    target = data_match.group("target")
    return (
        error_text.render(config, "market_target_data_mismatch_message", target=target),
        error_text.render(config, "market_target_data_mismatch_suggestion"),
    )


def _describe_trade_event_timeout(reason: str, config: AppConfig) -> tuple[str, str] | None:
    match = _MARKET_EVENT_TIMEOUT_RE.search(reason)
    if match is None:
        return None
    return (
        error_text.render(
            config,
            "trade_event_timeout_message",
            event_type=match.group("event_type"),
            target=match.group("target"),
            timeout_s=float(match.group("timeout_s")),
        ),
        error_text.render(config, "trade_event_timeout_suggestion"),
    )


def _clean_reason(reason: str) -> str:
    return reason[:1].upper() + reason[1:] if reason else "Unknown error"


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
