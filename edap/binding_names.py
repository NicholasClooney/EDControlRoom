from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BindingActionInfo:
    action: str
    label: str
    location: str | None = None


_ACTION_INFO: dict[str, BindingActionInfo] = {
    "SetSpeedZero": BindingActionInfo("SetSpeedZero", "Set Speed to 0%", "Ship Controls > Flight Throttle"),
    "SetSpeed100": BindingActionInfo("SetSpeed100", "Set Speed to 100%", "Ship Controls > Flight Throttle"),
    "HyperSuperCombination": BindingActionInfo(
        "HyperSuperCombination",
        "Toggle Frame Shift Drive",
        "Ship Controls > Flight Miscellaneous",
    ),
    "UseBoostJuice": BindingActionInfo("UseBoostJuice", "Engine Boost", "Ship Controls > Flight Miscellaneous"),
    "FocusLeftPanel": BindingActionInfo("FocusLeftPanel", "External Panel", "Ship Controls > Mode Switches"),
    "UIFocus": BindingActionInfo("UIFocus", "UI Focus", "Ship Controls > Mode Switches"),
    "UI_Up": BindingActionInfo("UI_Up", "UI Panel Up", "General Controls > Interface Mode"),
    "UI_Down": BindingActionInfo("UI_Down", "UI Panel Down", "General Controls > Interface Mode"),
    "UI_Left": BindingActionInfo("UI_Left", "UI Panel Left", "General Controls > Interface Mode"),
    "UI_Right": BindingActionInfo("UI_Right", "UI Panel Right", "General Controls > Interface Mode"),
    "UI_Select": BindingActionInfo("UI_Select", "UI Panel Select", "General Controls > Interface Mode"),
    "UI_Back": BindingActionInfo("UI_Back", "UI Back", "General Controls > Interface Mode"),
    "CycleNextPanel": BindingActionInfo("CycleNextPanel", "Next Panel Tab", "General Controls > Interface Mode"),
    "CyclePreviousPanel": BindingActionInfo(
        "CyclePreviousPanel",
        "Previous Panel Tab",
        "General Controls > Interface Mode",
    ),
    "HeadLookReset": BindingActionInfo("HeadLookReset", "Reset Headlook", "Ship Controls > Headlook Mode"),
    "MouseReset": BindingActionInfo("MouseReset", "Reset Mouse", "Ship Controls > Mouse Controls"),
    "PrimaryFire": BindingActionInfo("PrimaryFire", "Primary Fire", "Ship Controls > Weapons"),
    "SecondaryFire": BindingActionInfo("SecondaryFire", "Secondary Fire", "Ship Controls > Weapons"),
    "RollLeftButton": BindingActionInfo("RollLeftButton", "Roll Left", "Ship Controls > Flight Rotation"),
    "RollRightButton": BindingActionInfo("RollRightButton", "Roll Right", "Ship Controls > Flight Rotation"),
    "PitchUpButton": BindingActionInfo("PitchUpButton", "Pitch Up", "Ship Controls > Flight Rotation"),
    "PitchDownButton": BindingActionInfo("PitchDownButton", "Pitch Down", "Ship Controls > Flight Rotation"),
    "YawLeftButton": BindingActionInfo("YawLeftButton", "Yaw Left", "Ship Controls > Flight Rotation"),
    "YawRightButton": BindingActionInfo("YawRightButton", "Yaw Right", "Ship Controls > Flight Rotation"),
    "GalaxyMapOpen": BindingActionInfo("GalaxyMapOpen", "Open Galaxy Map", "Ship Controls > Mode Switches"),
    "CamZoomIn": BindingActionInfo("CamZoomIn", "Zoom In", "General Controls > Galaxy Map"),
}


def get_binding_action_info(action: str) -> BindingActionInfo:
    return _ACTION_INFO.get(action, BindingActionInfo(action=action, label=action))


def format_binding_action_hint(action: str) -> str:
    info = get_binding_action_info(action)
    if info.location:
        return f"{info.label} ({info.location})"
    return info.label
