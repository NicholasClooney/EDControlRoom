from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping
from xml.etree.ElementTree import parse

from edap.bindings import Binding, REQUIRED_BINDINGS, read_bindings


KEY_ALIASES = {
    "Space": "space",
    "Comma": ",",
    "Period": ".",
    "Slash": "/",
    "Backslash": "\\",
    "Semicolon": ";",
    "Quote": "'",
    "Minus": "-",
    "Equals": "=",
    "LeftBracket": "[",
    "RightBracket": "]",
    "Return": "enter",
    "Enter": "enter",
    "Tab": "tab",
    "Escape": "escape",
    "Esc": "escape",
    "Backspace": "backspace",
    "Delete": "delete",
    "Insert": "insert",
    "Home": "home",
    "End": "end",
    "PageUp": "page_up",
    "PageDown": "page_down",
    "UpArrow": "up",
    "DownArrow": "down",
    "LeftArrow": "left",
    "RightArrow": "right",
    "LeftShift": "left_shift",
    "RightShift": "right_shift",
    "LeftAlt": "left_alt",
    "RightAlt": "right_alt",
    "LeftControl": "left_control",
    "RightControl": "right_control",
}
CANONICAL_TOKENS = set(KEY_ALIASES.values())
DEFAULT_MISSING_REASON = "no keyboard binding was resolved for this action"


@dataclass(frozen=True)
class NormalizedBinding:
    key: str
    modifier: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True)
class BindingLookupResult:
    action: str
    status: str
    binding: NormalizedBinding | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "action": self.action,
            "status": self.status,
        }
        if self.binding is not None:
            payload["binding"] = self.binding.to_dict()
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


class BindingLookup:
    def __init__(self, results: Mapping[str, BindingLookupResult]) -> None:
        self._results = dict(results)

    def resolve(self, action: str) -> BindingLookupResult:
        return self._results.get(
            action,
            BindingLookupResult(
                action=action,
                status="missing",
                reason="action was not loaded into the binding lookup",
            ),
        )

    def get(self, action: str) -> NormalizedBinding | None:
        result = self.resolve(action)
        return result.binding if result.status == "ok" else None

    def supported_actions(self) -> dict[str, NormalizedBinding]:
        return {
            action: result.binding
            for action, result in self._results.items()
            if result.status == "ok" and result.binding is not None
        }

    def issues(self) -> dict[str, BindingLookupResult]:
        return {
            action: result
            for action, result in self._results.items()
            if result.status != "ok"
        }

    def to_dict(self) -> dict[str, dict[str, object]]:
        return {
            action: result.to_dict()
            for action, result in sorted(self._results.items())
        }


def normalize_action_binding(binding: Binding) -> NormalizedBinding:
    key = normalize_internal_key_name(binding.key, role="key")
    modifier = normalize_internal_key_name(binding.modifier, role="modifier") if binding.modifier else None
    return NormalizedBinding(key=key, modifier=modifier)


def normalize_internal_key_name(token: str, *, role: str = "key") -> str:
    token = token.strip()
    if token in CANONICAL_TOKENS:
        return token
    if token.startswith("Key_"):
        token = token[4:]
    if token in KEY_ALIASES:
        return KEY_ALIASES[token]
    if len(token) == 1 and token.isalnum():
        return token.lower()
    if token.startswith("NumPad") and token[6:].isdigit():
        return f"numpad_{token[6:]}"
    if token.startswith("F") and token[1:].isdigit():
        return token.lower()
    if token.isalpha():
        return token.lower()
    raise ValueError(f"unsupported {role} binding token: {token}")


def _coerce_missing_action_reasons(missing_actions: Iterable[str] | Mapping[str, str]) -> dict[str, str]:
    if isinstance(missing_actions, Mapping):
        return dict(missing_actions)
    return {action: DEFAULT_MISSING_REASON for action in missing_actions}


def _describe_missing_binding_reasons(bindings_file: Path, actions: Iterable[str]) -> dict[str, str]:
    wanted = set(actions)
    if not wanted:
        return {}

    bindings_root = parse(bindings_file).getroot()
    reasons: dict[str, str] = {action: "action is not present in bindings file" for action in wanted}

    for item in bindings_root:
        if item.tag not in wanted:
            continue

        keyboard_children = [
            child for child in item if child.attrib.get("Device", "").strip() == "Keyboard"
        ]
        if not keyboard_children:
            if len(item) == 0:
                reasons[item.tag] = "action has no binding entries in the bindings file"
            else:
                reasons[item.tag] = "action has bindings, but none are keyboard bindings"
            continue

        if all(not child.attrib.get("Key") for child in keyboard_children):
            reasons[item.tag] = "keyboard binding is present, but its key token is missing"
            continue

        reasons[item.tag] = DEFAULT_MISSING_REASON

    return reasons


def build_binding_lookup(
    bindings: Mapping[str, Binding],
    missing_actions: Iterable[str] | Mapping[str, str] = (),
    actions: Iterable[str] | None = None,
) -> BindingLookup:
    wanted = list(actions or REQUIRED_BINDINGS)
    missing = _coerce_missing_action_reasons(missing_actions)
    results: dict[str, BindingLookupResult] = {}

    for action in wanted:
        binding = bindings.get(action)
        if binding is None or action in missing:
            results[action] = BindingLookupResult(
                action=action,
                status="missing",
                reason=missing.get(action, DEFAULT_MISSING_REASON),
            )
            continue
        try:
            normalized = normalize_action_binding(binding)
        except ValueError as exc:
            results[action] = BindingLookupResult(
                action=action,
                status="unsupported",
                reason=str(exc),
            )
            continue
        results[action] = BindingLookupResult(
            action=action,
            status="ok",
            binding=normalized,
        )

    return BindingLookup(results)


def load_binding_lookup(bindings_file: Path, actions: list[str] | None = None) -> BindingLookup:
    bindings, missing = read_bindings(bindings_file, keys_to_obtain=actions)
    missing_reasons = _describe_missing_binding_reasons(bindings_file, missing)
    return build_binding_lookup(bindings, missing_actions=missing_reasons, actions=actions)
