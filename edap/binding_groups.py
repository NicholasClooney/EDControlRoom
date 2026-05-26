"""Grouping logic for the static bindings TUI viewer.

This module is intentionally rendering-agnostic: it produces a structured
``list[BindingGroup]`` from a binding lookup result so that the rendering
layer in ``view_bindings.py`` can stay thin and the grouping is unit-testable
without importing ``rich``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from edap.binding_lookup import BindingLookupResult, NormalizedBinding


# Display order matters. Each entry is (group title, ordered list of action names).
GROUPS: list[tuple[str, list[str]]] = [
    (
        "Roll & Throttle",
        [
            "RollLeftButton",
            "RollRightButton",
            "SetSpeedZero",
            "SetSpeed100",
        ],
    ),
    (
        "Pitch & Yaw",
        [
            "PitchUpButton",
            "PitchDownButton",
            "YawLeftButton",
            "YawRightButton",
        ],
    ),
    (
        "UI Navigation",
        [
            "UI_Up",
            "UI_Down",
            "UI_Left",
            "UI_Right",
            "UI_Select",
            "UI_Back",
            "UIFocus",
            "CycleNextPanel",
        ],
    ),
    (
        "Combat & Targeting",
        [
            "PrimaryFire",
            "SecondaryFire",
            "MouseReset",
        ],
    ),
    (
        "Cockpit & Travel",
        [
            "HyperSuperCombination",
            "HeadLookReset",
        ],
    ),
]


UNMAPPED_TITLE = "Unmapped"


@dataclass(frozen=True)
class BindingRow:
    """One row inside a rendered group."""

    action: str
    status: str  # "ok", "missing", "unsupported"
    key: str | None = None
    modifier: str | None = None
    reason: str | None = None

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class BindingGroup:
    """A titled group of rows in display order."""

    title: str
    rows: list[BindingRow] = field(default_factory=list)
    is_unmapped: bool = False


def group_bindings(
    supported: Mapping[str, NormalizedBinding],
    issues: Mapping[str, BindingLookupResult],
) -> list[BindingGroup]:
    """Bucket binding lookup results into ordered display groups.

    Supported actions land in their declared group with status ``ok``. Any
    action with an issue (missing or unsupported) is collected into the
    trailing ``Unmapped`` group instead of staying in its category, so the
    user can scan the per-category panels without seeing red noise mixed in.
    The ``Unmapped`` group is omitted entirely when nothing is missing.
    """

    groups: list[BindingGroup] = []
    unmapped_rows: list[BindingRow] = []

    for title, action_names in GROUPS:
        rows: list[BindingRow] = []
        for action in action_names:
            binding = supported.get(action)
            if binding is not None:
                rows.append(
                    BindingRow(
                        action=action,
                        status="ok",
                        key=binding.key,
                        modifier=binding.modifier,
                    )
                )
                continue

            issue = issues.get(action)
            if issue is not None:
                unmapped_rows.append(
                    BindingRow(
                        action=action,
                        status=issue.status,
                        reason=issue.reason,
                    )
                )
                continue

            # Action wasn't in either map. Treat as missing so the user can
            # still see it surface in the Unmapped panel.
            unmapped_rows.append(
                BindingRow(
                    action=action,
                    status="missing",
                    reason="action was not loaded into the binding lookup",
                )
            )

        groups.append(BindingGroup(title=title, rows=rows))

    if unmapped_rows:
        groups.append(
            BindingGroup(
                title=UNMAPPED_TITLE,
                rows=unmapped_rows,
                is_unmapped=True,
            )
        )

    return groups
