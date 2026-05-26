from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from edap.bindings import normalize_binding_token, read_bindings


class BindingsTests(unittest.TestCase):
    def test_normalize_binding_token_handles_key_prefix_and_modifiers(self) -> None:
        self.assertEqual(normalize_binding_token("Key_J"), "J")
        self.assertEqual(normalize_binding_token("Key_LeftShift"), "LeftShift")
        self.assertEqual(normalize_binding_token("Space"), "Space")
        self.assertIsNone(normalize_binding_token(None))

    def test_read_bindings_extracts_keyboard_bindings_and_missing_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            bindings_path = Path(temp_dir) / "Custom.binds"
            bindings_path.write_text(
                """
<Root>
  <YawLeftButton>
    <Primary Device="Keyboard" Key="Key_A" />
  </YawLeftButton>
  <HyperSuperCombination>
    <Primary Device="GamePad" Key="Pad_A" />
    <Secondary Device="Keyboard" Key="Key_J">
      <Modifier Device="Keyboard" Key="Key_LeftShift" />
    </Secondary>
  </HyperSuperCombination>
  <UI_Select>
    <Primary Device="Keyboard" Key="Space" />
  </UI_Select>
</Root>
""".strip(),
                encoding="utf-8",
            )

            bindings, missing = read_bindings(
                bindings_path,
                keys_to_obtain=["YawLeftButton", "HyperSuperCombination", "UI_Select", "UI_Back"],
            )

            self.assertEqual(bindings["YawLeftButton"].key, "A")
            self.assertEqual(bindings["HyperSuperCombination"].key, "J")
            self.assertEqual(bindings["HyperSuperCombination"].modifier, "LeftShift")
            self.assertEqual(bindings["UI_Select"].key, "Space")
            self.assertEqual(missing, ["UI_Back"])
