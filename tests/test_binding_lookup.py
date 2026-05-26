from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from edap.binding_lookup import (
    BindingLookupResult,
    build_binding_lookup,
    load_binding_lookup,
    normalize_internal_key_name,
)
from edap.bindings import Binding


class BindingLookupTests(unittest.TestCase):
    def test_normalize_internal_key_name_uses_backend_neutral_names(self) -> None:
        self.assertEqual(normalize_internal_key_name("A"), "a")
        self.assertEqual(normalize_internal_key_name("Key_A"), "a")
        self.assertEqual(normalize_internal_key_name("Space"), "space")
        self.assertEqual(normalize_internal_key_name("Comma"), ",")
        self.assertEqual(normalize_internal_key_name("Period"), ".")
        self.assertEqual(normalize_internal_key_name("LeftBracket"), "[")
        self.assertEqual(normalize_internal_key_name("RightBracket"), "]")
        self.assertEqual(normalize_internal_key_name("LeftShift"), "left_shift")
        self.assertEqual(normalize_internal_key_name("left_shift"), "left_shift")
        self.assertEqual(normalize_internal_key_name("F12"), "f12")
        self.assertEqual(normalize_internal_key_name("NumPad7"), "numpad_7")

    def test_build_binding_lookup_reports_ok_missing_and_unsupported(self) -> None:
        lookup = build_binding_lookup(
            bindings={
                "YawLeftButton": Binding(key="A"),
                "HyperSuperCombination": Binding(key="J", modifier="LeftShift"),
                "BadAction": Binding(key="Mouse_1"),
                "BadModifierAction": Binding(key="J", modifier="Mouse_1"),
            },
            missing_actions=["UI_Back"],
            actions=[
                "YawLeftButton",
                "HyperSuperCombination",
                "UI_Back",
                "BadAction",
                "BadModifierAction",
            ],
        )

        self.assertEqual(lookup.get("YawLeftButton").key, "a")
        self.assertEqual(lookup.get("HyperSuperCombination").modifier, "left_shift")
        self.assertEqual(lookup.resolve("UI_Back").status, "missing")
        self.assertEqual(lookup.resolve("BadAction").status, "unsupported")
        self.assertEqual(
            lookup.resolve("BadAction").reason,
            "unsupported key binding token: Mouse_1",
        )
        self.assertEqual(lookup.resolve("BadModifierAction").status, "unsupported")
        self.assertEqual(
            lookup.resolve("BadModifierAction").reason,
            "unsupported modifier binding token: Mouse_1",
        )

    def test_resolve_unknown_action_is_missing(self) -> None:
        lookup = build_binding_lookup(bindings={}, actions=["YawLeftButton"])

        result = lookup.resolve("SetSpeedZero")

        self.assertIsInstance(result, BindingLookupResult)
        self.assertEqual(result.status, "missing")
        self.assertEqual(result.reason, "action was not loaded into the binding lookup")

    def test_load_binding_lookup_reads_and_normalizes_bindings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            bindings_path = Path(temp_dir) / "Custom.binds"
            bindings_path.write_text(
                """
<Root>
  <YawLeftButton>
    <Primary Device="Keyboard" Key="Key_A" />
  </YawLeftButton>
  <HyperSuperCombination>
    <Primary Device="Keyboard" Key="Key_J">
      <Modifier Device="Keyboard" Key="Key_LeftShift" />
    </Primary>
  </HyperSuperCombination>
</Root>
""".strip(),
                encoding="utf-8",
            )

            lookup = load_binding_lookup(
                bindings_path,
                actions=["YawLeftButton", "HyperSuperCombination", "UI_Back"],
            )

            self.assertEqual(lookup.get("YawLeftButton").to_dict(), {"key": "a", "modifier": None})
            self.assertEqual(
                lookup.get("HyperSuperCombination").to_dict(),
                {"key": "j", "modifier": "left_shift"},
            )
            self.assertEqual(lookup.resolve("UI_Back").status, "missing")

    def test_load_binding_lookup_reports_non_keyboard_only_binding(self) -> None:
        with TemporaryDirectory() as temp_dir:
            bindings_path = Path(temp_dir) / "Custom.binds"
            bindings_path.write_text(
                """
<Root>
  <PrimaryFire>
    <Primary Device="Mouse" Key="Mouse_1" />
  </PrimaryFire>
</Root>
""".strip(),
                encoding="utf-8",
            )

            lookup = load_binding_lookup(bindings_path, actions=["PrimaryFire", "UI_Back"])

            self.assertEqual(lookup.resolve("PrimaryFire").status, "missing")
            self.assertEqual(
                lookup.resolve("PrimaryFire").reason,
                "action has bindings, but none are keyboard bindings",
            )
            self.assertEqual(
                lookup.resolve("UI_Back").reason,
                "action is not present in bindings file",
            )

    def test_load_binding_lookup_reports_keyboard_binding_with_missing_key_token(self) -> None:
        with TemporaryDirectory() as temp_dir:
            bindings_path = Path(temp_dir) / "Custom.binds"
            bindings_path.write_text(
                """
<Root>
  <UI_Select>
    <Primary Device="Keyboard" />
  </UI_Select>
</Root>
""".strip(),
                encoding="utf-8",
            )

            lookup = load_binding_lookup(bindings_path, actions=["UI_Select"])

            self.assertEqual(lookup.resolve("UI_Select").status, "missing")
            self.assertEqual(
                lookup.resolve("UI_Select").reason,
                "keyboard binding is present, but its key token is missing",
            )
