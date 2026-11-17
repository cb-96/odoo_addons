#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "duty_allocation", ROOT / "sports_federation_officiating" / "duty_allocation.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(assignment, fixture, start, end, roles, opponents):
    return {
        "assignment": assignment,
        "fixture": fixture,
        "start": start,
        "end": end,
        "duration_minutes": 60,
        "roles": roles,
        "opponents": opponents,
        "resolved": True,
        "existing_clubs": [],
    }


class CapacityAwareDutyAllocationTest(unittest.TestCase):
    def test_simultaneous_capacity_is_a_hard_constraint(self):
        rows = [
            row(1, 1, "2026-11-17 10:00:00", "2026-11-17 11:00:00", ["head"], [1, 2]),
            row(2, 2, "2026-11-17 10:00:00", "2026-11-17 11:00:00", ["head"], [1, 2]),
            row(3, 3, "2026-11-17 12:00:00", "2026-11-17 13:00:00", [], [3, 4]),
        ]
        result = MODULE.allocate(
            rows,
            avoid_playing=False,
            capacities={
                1: {"max_simultaneous": 1, "roles": ["head"]},
                2: {"max_simultaneous": 1, "roles": ["head"]},
                3: {"max_simultaneous": 1, "roles": ["head"]},
                4: {"max_simultaneous": 1, "roles": ["head"]},
            },
            pins={1: 3, 2: 3},
        )
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["issue_details"][0]["code"], "pin_conflict")
        self.assertIn("capacity", result["issue_details"][0]["message"])

    def test_role_qualification_explains_rejection(self):
        result = MODULE.allocate(
            [
                row(
                    1, 1, "2026-11-17 10:00:00", "2026-11-17 11:00:00", ["head"], [1, 2]
                ),
                row(2, 2, "2026-11-17 12:00:00", "2026-11-17 13:00:00", [], [3, 4]),
            ],
            avoid_playing=False,
            capacities={
                3: {"max_simultaneous": 2, "roles": ["table"]},
                4: {"max_simultaneous": 2, "roles": ["table"]},
            },
        )
        self.assertFalse(result["rows"])
        rejected = result["issue_details"][0]["rejected"]
        self.assertIn("missing qualifications", rejected[3])

    def test_manual_pin_survives_recalculation(self):
        rows = [
            row(1, 10, "2026-11-17 10:00:00", "2026-11-17 11:00:00", ["table"], [1, 2])
        ]
        policies = {
            1: {"max_simultaneous": 2, "roles": ["table"]},
            2: {"max_simultaneous": 2, "roles": ["table"]},
            3: {"max_simultaneous": 2, "roles": ["table"]},
            4: {"max_simultaneous": 2, "roles": ["table"]},
        }
        # Clubs are discovered from participating clubs. Add a concurrent row
        # with no missing roles so club 4 is in the candidate universe.
        rows.append(
            row(2, 11, "2026-11-17 12:00:00", "2026-11-17 13:00:00", [], [3, 4])
        )
        result = MODULE.allocate(
            rows, avoid_playing=False, capacities=policies, pins={10: 4}
        )
        self.assertEqual(result["rows"][0]["club"], 4)
        self.assertTrue(result["rows"][0]["pinned"])

    def test_workload_reports_roles_and_minutes(self):
        rows = [
            row(
                1,
                1,
                "2026-11-17 10:00:00",
                "2026-11-17 11:00:00",
                ["head", "table"],
                [1, 2],
            )
        ]
        rows.append(row(2, 2, "2026-11-17 12:00:00", "2026-11-17 13:00:00", [], [3, 4]))
        result = MODULE.allocate(rows, avoid_playing=False)
        assigned = str(result["rows"][0]["club"])
        self.assertEqual(result["load"][assigned], 2)
        self.assertEqual(result["minute_load"][assigned], 120)


if __name__ == "__main__":
    unittest.main()
