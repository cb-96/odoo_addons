#!/usr/bin/env python3
"""Run planning evidence fingerprint tests without an Odoo registry."""

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "planning_fingerprint",
    ROOT / "sports_federation_scheduling" / "planning_fingerprint.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PlanningFingerprintTest(unittest.TestCase):
    def test_mapping_order_does_not_change_digest(self):
        self.assertEqual(
            MODULE.fingerprint({"configuration": {"weight": 2}, "fixtures": [3, 1]}),
            MODULE.fingerprint({"fixtures": [3, 1], "configuration": {"weight": 2}}),
        )

    def test_material_input_change_changes_digest(self):
        baseline = {"revision": 4, "slots": [[10, "2026-11-18 10:00:00"]]}
        changed = {"revision": 4, "slots": [[10, "2026-11-18 10:05:00"]]}
        self.assertNotEqual(MODULE.fingerprint(baseline), MODULE.fingerprint(changed))

    def test_datetime_like_values_are_serialized_deterministically(self):
        class Value:
            def __str__(self):
                return "2026-11-18 10:00:00"

        self.assertEqual(
            MODULE.fingerprint({"start": Value()}),
            MODULE.fingerprint({"start": "2026-11-18 10:00:00"}),
        )


if __name__ == "__main__":
    unittest.main()
