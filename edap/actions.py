from __future__ import annotations

from dataclasses import asdict, dataclass

from edap.binding_lookup import BindingLookup, BindingLookupResult, NormalizedBinding
from edap.platform.input.base import InputController


@dataclass(frozen=True)
class ActionDispatchResult:
    action: str
    status: str
    binding: NormalizedBinding | None = None
    repeat: int = 0
    hold_s: float = 0.0
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        if self.binding is not None:
            payload["binding"] = self.binding.to_dict()
        return payload


class ActionDispatcher:
    def __init__(self, binding_lookup: BindingLookup, input_controller: InputController) -> None:
        self._binding_lookup = binding_lookup
        self._input_controller = input_controller

    def tap_action(self, action: str, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        if repeat < 1:
            raise ValueError("repeat must be at least 1")
        if hold_s < 0:
            raise ValueError("hold_s must be non-negative")

        resolved = self._binding_lookup.resolve(action)
        if resolved.status != "ok" or resolved.binding is None:
            return self._result_from_lookup(resolved, repeat=repeat, hold_s=hold_s)

        for _ in range(repeat):
            self._input_controller.tap_key(
                resolved.binding.key,
                modifier=resolved.binding.modifier,
                hold_s=hold_s,
            )
        return ActionDispatchResult(
            action=action,
            status="ok",
            binding=resolved.binding,
            repeat=repeat,
            hold_s=hold_s,
        )

    def type_text(self, text: str, char_delay_s: float = 0.05) -> None:
        self._input_controller.type_text(text, char_delay_s=char_delay_s)

    def _result_from_lookup(
        self,
        resolved: BindingLookupResult,
        repeat: int,
        hold_s: float,
    ) -> ActionDispatchResult:
        return ActionDispatchResult(
            action=resolved.action,
            status=resolved.status,
            binding=resolved.binding,
            repeat=repeat,
            hold_s=hold_s,
            reason=resolved.reason,
        )
