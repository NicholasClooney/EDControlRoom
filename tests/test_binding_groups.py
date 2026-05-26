from __future__ import annotations

import unittest

from edap.binding_groups import (
    GROUPS,
    UNMAPPED_TITLE,
    BindingRow,
    group_bindings,
)
from edap.binding_lookup import BindingLookupResult, NormalizedBinding
from edap.bindings import REQUIRED_BINDINGS


class GroupCoverageTests(unittest.TestCase):
    def test_groups_cover_required_bindings_exactly_once(self) -> None:
        grouped_actions: list[str] = []
        for _title, actions in GROUPS:
            grouped_actions.extend(actions)

        self.assertEqual(
            sorted(grouped_actions),
            sorted(REQUIRED_BINDINGS),
            "GROUPS must cover every REQUIRED_BINDINGS action exactly once",
        )
        self.assertEqual(
            len(grouped_actions),
            len(set(grouped_actions)),
            "GROUPS must not contain duplicate action names",
        )


class GroupBindingsTests(unittest.TestCase):
    def _supported(self, **bindings: NormalizedBinding) -> dict[str, NormalizedBinding]:
        return dict(bindings)

    def _issue(self, action: str, status: str = "missing", reason: str = "") -> BindingLookupResult:
        return BindingLookupResult(action=action, status=status, reason=reason or status)

    def test_supported_action_lands_in_its_declared_group(self) -> None:
        supported = self._supported(
            RollLeftButton=NormalizedBinding(key="a"),
            HyperSuperCombination=NormalizedBinding(key="j", modifier="left_shift"),
        )
        # Everything else is missing; we'll just supply empty issues for the
        # actions we care about asserting against and trust the function to
        # collect the rest into Unmapped.
        issues: dict[str, BindingLookupResult] = {
            action: self._issue(action)
            for action in REQUIRED_BINDINGS
            if action not in supported
        }

        groups = group_bindings(supported, issues)
        by_title = {g.title: g for g in groups}

        roll_throttle = by_title["Roll & Throttle"]
        roll_row = next(r for r in roll_throttle.rows if r.action == "RollLeftButton")
        self.assertEqual(roll_row.status, "ok")
        self.assertEqual(roll_row.key, "a")
        self.assertIsNone(roll_row.modifier)

        cockpit = by_title["Cockpit & Travel"]
        hyper_row = next(r for r in cockpit.rows if r.action == "HyperSuperCombination")
        self.assertEqual(hyper_row.status, "ok")
        self.assertEqual(hyper_row.key, "j")
        self.assertEqual(hyper_row.modifier, "left_shift")

    def test_missing_action_moves_to_unmapped_not_original_group(self) -> None:
        supported = self._supported(
            RollLeftButton=NormalizedBinding(key="a"),
        )
        issues = {
            "PitchUpButton": self._issue("PitchUpButton", reason="action is not present in bindings file"),
        }
        # Fill the rest of REQUIRED_BINDINGS in as supported to keep the test
        # focused on the one missing action's placement.
        for action in REQUIRED_BINDINGS:
            if action in supported or action in issues:
                continue
            supported[action] = NormalizedBinding(key="z")

        groups = group_bindings(supported, issues)
        by_title = {g.title: g for g in groups}

        pitch_yaw = by_title["Pitch & Yaw"]
        pitch_actions = [r.action for r in pitch_yaw.rows]
        self.assertNotIn(
            "PitchUpButton",
            pitch_actions,
            "missing actions should not appear in their original category group",
        )

        self.assertIn(UNMAPPED_TITLE, by_title)
        unmapped = by_title[UNMAPPED_TITLE]
        self.assertTrue(unmapped.is_unmapped)
        unmapped_actions = {r.action: r for r in unmapped.rows}
        self.assertIn("PitchUpButton", unmapped_actions)
        self.assertEqual(unmapped_actions["PitchUpButton"].status, "missing")
        self.assertEqual(
            unmapped_actions["PitchUpButton"].reason,
            "action is not present in bindings file",
        )

    def test_unmapped_group_only_appears_when_something_is_missing(self) -> None:
        supported = {
            action: NormalizedBinding(key="a") for action in REQUIRED_BINDINGS
        }
        groups = group_bindings(supported, {})
        titles = [g.title for g in groups]
        self.assertNotIn(UNMAPPED_TITLE, titles)
        # All declared groups still render.
        self.assertEqual(titles, [title for title, _ in GROUPS])

    def test_unsupported_action_lands_in_unmapped_with_reason(self) -> None:
        supported = {
            action: NormalizedBinding(key="a")
            for action in REQUIRED_BINDINGS
            if action != "PrimaryFire"
        }
        issues = {
            "PrimaryFire": BindingLookupResult(
                action="PrimaryFire",
                status="unsupported",
                reason="unsupported key binding token: Mouse_1",
            ),
        }
        groups = group_bindings(supported, issues)
        by_title = {g.title: g for g in groups}

        combat = by_title["Combat & Targeting"]
        self.assertNotIn("PrimaryFire", [r.action for r in combat.rows])

        unmapped = by_title[UNMAPPED_TITLE]
        row = next(r for r in unmapped.rows if r.action == "PrimaryFire")
        self.assertEqual(row.status, "unsupported")
        self.assertEqual(row.reason, "unsupported key binding token: Mouse_1")


if __name__ == "__main__":
    unittest.main()
