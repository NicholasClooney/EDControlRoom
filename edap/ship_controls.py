from __future__ import annotations

from pathlib import Path

from edap.actions import ActionDispatchResult, ActionDispatcher
from edap.binding_lookup import BindingLookup, load_binding_lookup
from edap.platform.input.base import InputController


class ShipControls:
    """Narrow runtime-facing ship control wrapper for binding-driven actions."""

    def __init__(self, dispatcher: ActionDispatcher) -> None:
        self._dispatcher = dispatcher

    @classmethod
    def from_binding_lookup(
        cls,
        binding_lookup: BindingLookup,
        input_controller: InputController,
    ) -> ShipControls:
        return cls(ActionDispatcher(binding_lookup, input_controller))

    @classmethod
    def from_bindings_file(
        cls,
        bindings_file: Path,
        input_controller: InputController,
        actions: list[str] | None = None,
    ) -> ShipControls:
        binding_lookup = load_binding_lookup(bindings_file, actions=actions or ["SetSpeedZero"])
        return cls.from_binding_lookup(binding_lookup, input_controller)

    def tap_action(self, action: str, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self._dispatcher.tap_action(action, repeat=repeat, hold_s=hold_s)

    def set_speed_zero(self, repeat: int = 1, hold_s: float = 0.0) -> ActionDispatchResult:
        return self.tap_action("SetSpeedZero", repeat=repeat, hold_s=hold_s)
