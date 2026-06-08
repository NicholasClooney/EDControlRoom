from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from edap.status import StatusFlags, read_status


class StatusFlagsTests(unittest.TestCase):
    def test_zero_flags_all_false(self) -> None:
        flags = StatusFlags.from_int(0)
        for field in flags.__dataclass_fields__:
            self.assertFalse(getattr(flags, field), f"{field} should be False")

    def test_fsd_mass_locked_bit_16(self) -> None:
        flags = StatusFlags.from_int(1 << 16)
        self.assertTrue(flags.fsd_mass_locked)
        self.assertFalse(flags.supercruise)

    def test_supercruise_bit_4(self) -> None:
        flags = StatusFlags.from_int(1 << 4)
        self.assertTrue(flags.supercruise)
        self.assertFalse(flags.fsd_mass_locked)

    def test_multiple_flags(self) -> None:
        # Docked + Shields Up + In Main Ship
        flags = StatusFlags.from_int((1 << 0) | (1 << 3) | (1 << 24))
        self.assertTrue(flags.docked)
        self.assertTrue(flags.shields_up)
        self.assertTrue(flags.in_main_ship)
        self.assertFalse(flags.landed)

    def test_known_example_from_docs(self) -> None:
        # 16842765 == Docked + Landing Gear Down + Shields Up + Mass Locked + In Main Ship
        flags = StatusFlags.from_int(16842765)
        self.assertTrue(flags.docked)
        self.assertTrue(flags.shields_up)
        self.assertTrue(flags.fsd_mass_locked)
        self.assertTrue(flags.in_main_ship)

    def test_all_32_bits_distinct(self) -> None:
        for bit in range(32):
            flags = StatusFlags.from_int(1 << bit)
            true_fields = [f for f in flags.__dataclass_fields__ if getattr(flags, f)]
            self.assertEqual(len(true_fields), 1, f"bit {bit} should set exactly one flag, got {true_fields}")


class ReadStatusTests(unittest.TestCase):
    def test_returns_none_when_file_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            result = read_status(Path(tmp))
            self.assertIsNone(result)

    def test_returns_none_when_file_empty(self) -> None:
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "Status.json").write_text("", encoding="utf-8")
            result = read_status(Path(tmp))
            self.assertIsNone(result)

    def test_parses_flags_and_fuel(self) -> None:
        with TemporaryDirectory() as tmp:
            data = {
                "timestamp": "2024-01-01T00:00:00Z",
                "event": "Status",
                "Flags": (1 << 16) | (1 << 3),  # FsdMassLocked + ShieldsUp
                "Pips": [4, 4, 4],
                "FireGroup": 0,
                "GuiFocus": 0,
                "Fuel": {"FuelMain": 12.5, "FuelReservoir": 0.4},
                "Cargo": 32.0,
                "LegalState": "Clean",
                "Balance": 1000000,
                "Destination": {
                    "System": "Achenar",
                    "Body": "Dawes Hub",
                    "Name": "Dawes Hub",
                },
            }
            (Path(tmp) / "Status.json").write_text(json.dumps(data), encoding="utf-8")
            result = read_status(Path(tmp))

            self.assertIsNotNone(result)
            self.assertTrue(result.flags.fsd_mass_locked)
            self.assertTrue(result.flags.shields_up)
            self.assertFalse(result.flags.supercruise)
            self.assertEqual(result.pips_sys, 4)
            self.assertEqual(result.pips_eng, 4)
            self.assertEqual(result.pips_wep, 4)
            self.assertAlmostEqual(result.fuel_main, 12.5)
            self.assertAlmostEqual(result.fuel_reservoir, 0.4)
            self.assertEqual(result.cargo, 32.0)
            self.assertEqual(result.legal_state, "Clean")
            self.assertEqual(result.balance, 1000000)
            self.assertEqual(result.destination_system, "Achenar")
            self.assertEqual(result.destination_body, "Dawes Hub")
            self.assertEqual(result.destination_name, "Dawes Hub")
            self.assertEqual(result.raw_flags, (1 << 16) | (1 << 3))

    def test_parses_minimal_status(self) -> None:
        with TemporaryDirectory() as tmp:
            data = {"timestamp": "2024-01-01T00:00:00Z", "event": "Status", "Flags": 0}
            (Path(tmp) / "Status.json").write_text(json.dumps(data), encoding="utf-8")
            result = read_status(Path(tmp))

            self.assertIsNotNone(result)
            self.assertEqual(result.raw_flags, 0)
            self.assertIsNone(result.pips_sys)
            self.assertIsNone(result.fuel_main)

    def test_coerces_numeric_destination_fields_to_text(self) -> None:
        with TemporaryDirectory() as tmp:
            data = {
                "timestamp": "2024-01-01T00:00:00Z",
                "event": "Status",
                "Flags": 0,
                "Destination": {
                    "System": 670149518737,
                    "Body": 31,
                    "Name": "Pawelczyk Dock",
                },
            }
            (Path(tmp) / "Status.json").write_text(json.dumps(data), encoding="utf-8")

            result = read_status(Path(tmp))

            self.assertIsNotNone(result)
            self.assertEqual(result.destination_system, "670149518737")
            self.assertEqual(result.destination_body, "31")
            self.assertEqual(result.destination_name, "Pawelczyk Dock")
