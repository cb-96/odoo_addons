#!/usr/bin/env python3
"""Run allocation regression tests without an Odoo server."""

import importlib.util
import json
from pathlib import Path
import unittest

path = (
    Path(__file__).resolve().parents[1]
    / "sports_federation_officiating/duty_allocation.py"
)
spec = importlib.util.spec_from_file_location("duty_allocation", path)
allocation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(allocation)


def row(key, opponents, start=10, end=11, roles=None, existing=None):
    return {
        "assignment": key,
        "fixture": key,
        "opponents": opponents,
        "start": start,
        "end": end,
        "roles": ["head"] if roles is None else roles,
        "existing_clubs": existing or [],
    }


class TestAllocation(unittest.TestCase):
    def test_never_assigns_an_opponent(self):
        result = allocation.allocate([row(1, [1, 2]), row(2, [3, 4], 12, 13)])
        self.assertFalse(result["issues"])
        for item in result["rows"]:
            self.assertNotIn(item["club"], item["opponents"])

    def test_strict_overlap_blocks(self):
        result = allocation.allocate([row(1, [1, 2]), row(2, [3, 4])])
        self.assertEqual(len(result["issues"]), 2)

    def test_fallback_is_explicit_and_visible(self):
        rows = [row(1, [1, 2]), row(2, [3, 4])]
        result = allocation.allocate(rows, allow_fallback=True)
        self.assertFalse(result["issues"])
        self.assertTrue(all(item["fallback"] for item in result["rows"]))

    def test_adjacent_slots_do_not_overlap(self):
        result = allocation.allocate([row(1, [1, 2]), row(2, [3, 4], 11, 12)])
        self.assertFalse(result["issues"])

    def test_partial_overlap_counts(self):
        result = allocation.allocate([row(1, [1, 2]), row(2, [3, 4], 10.5, 12)])
        self.assertEqual(len(result["issues"]), 2)

    def test_unknown_participants_block(self):
        result = allocation.allocate([row(1, [1]), row(2, [3, 4], 12, 13)])
        self.assertTrue(result["issues"])

    def test_two_known_teams_from_same_club_are_supported(self):
        first = dict(row(1, [1]), resolved=True)
        result = allocation.allocate([first, row(2, [3, 4], 12, 13)])
        self.assertFalse(result["issues"])
        self.assertNotEqual(result["rows"][0]["club"], 1)

    def test_no_roles_means_no_duties(self):
        self.assertFalse(allocation.allocate([row(1, [1, 2], roles=[])])["rows"])

    def test_multiple_roles_use_one_club(self):
        result = allocation.allocate(
            [row(1, [1, 2], roles=["head", "assistant_1"]), row(2, [3, 4], 12, 13)]
        )
        self.assertEqual(result["rows"][0]["roles"], ["head", "assistant_1"])

    def test_existing_workload_is_counted_per_role(self):
        result = allocation.allocate(
            [row(1, [1, 2]), row(2, [3, 4], 12, 13, roles=[], existing=[3, 3])]
        )
        self.assertEqual(result["rows"][0]["club"], 4)
        self.assertEqual(result["load"]["3"], 2)

    def test_json_roundtrip_preserves_comparison(self):
        result = allocation.allocate([row(1, [1, 2]), row(2, [3, 4], 12, 13)])
        self.assertEqual(result, json.loads(json.dumps(result)))

    def test_deterministic_and_non_mutating(self):
        rows = [row(1, [1, 2]), row(2, [3, 4], 12, 13)]
        before = json.dumps(rows)
        self.assertEqual(
            allocation.allocate(rows), allocation.allocate(list(reversed(rows)))
        )
        self.assertEqual(before, json.dumps(rows))


if __name__ == "__main__":
    unittest.main()
