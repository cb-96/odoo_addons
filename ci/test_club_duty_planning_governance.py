#!/usr/bin/env python3
"""Contract tests for preserved-duty capacity, suggested fixes and the exact
optimizer; no Odoo needed. The optimizer tests run when OR-Tools is installed."""

import pathlib
import sys
import unittest

ADDON = pathlib.Path(__file__).resolve().parents[1] / "sports_federation_officiating"
sys.path.insert(0, str(ADDON))

import duty_allocation  # noqa: E402
import duty_exact_solver as exact  # noqa: E402
import duty_explanations as explanations  # noqa: E402
import duty_season_balance as balance  # noqa: E402

T10 = ("2026-11-21 10:00:00", "2026-11-21 11:00:00")
T12 = ("2026-11-21 12:00:00", "2026-11-21 13:00:00")
T14 = ("2026-11-21 14:00:00", "2026-11-21 15:00:00")


def fixture(number, slot, opponents, roles=("table",), existing=()):
    return {
        "assignment": number,
        "fixture": number,
        "start": slot[0],
        "end": slot[1],
        "duration_minutes": 60,
        "roles": list(roles),
        "opponents": list(opponents),
        "resolved": True,
        "existing_clubs": list(existing),
    }


def duty(number, club, slot, opponents, pinned=False):
    return dict(
        fixture(number, slot, opponents), club=club, fallback=False, pinned=pinned
    )


def clubs(rows):
    return [row["club"] for row in rows]


GEOMETRY_EXTRA = [fixture(1, T10, (1, 2), roles=())]


class PreservedCapacityTest(unittest.TestCase):
    def test_allocator_counts_preserved_duties(self):
        rows = [
            fixture(1, T10, (1, 2), roles=(), existing=(3,)),
            fixture(2, T10, (5, 6)),
            fixture(3, T12, (3, 4), roles=()),
        ]
        capacities = {
            3: {"max_simultaneous": 1, "roles": ["table"]},
            4: {"max_simultaneous": 1, "roles": ["head"]},
        }
        result = duty_allocation.allocate(rows, capacities=capacities)
        self.assertFalse(result["rows"])
        detail = result["issue_details"][0]
        self.assertEqual(detail["code"], "capacity_conflict")
        self.assertIn("simultaneous capacity", detail["rejected"][3])

    def test_rebalance_counts_preserved_duties(self):
        rows = [duty(2, 1, T12, (3, 4)), duty(3, 1, T14, (5, 6))]
        preserved = [dict(duty(2, 2, T12, (3, 4)), role="table", state="open")]
        result, _report = balance.rebalance_season(
            rows,
            rows + GEOMETRY_EXTRA,
            capacities={2: {"max_simultaneous": 1, "roles": ["table"]}},
            season_minutes={1: 600},
            targets={1: 300, 2: 300},
            fixed_rows=preserved,
        )
        self.assertEqual(clubs(result), [1, 2])
        self.assertEqual([row["allocated_club"] for row in result], [1, 1])


class SuggestionTest(unittest.TestCase):
    def test_capacity_conflict_suggestions(self):
        detail = {
            "code": "capacity_conflict",
            "rejected": {
                3: "simultaneous capacity 1 would be exceeded",
                4: "missing qualifications for table",
            },
        }
        self.assertEqual(
            explanations.suggestions(detail, {"avoid": True, "fallback": True}),
            [
                "raise_capacity",
                "shorten_buffers",
                "qualify_roles",
                "move_fixture",
                "assign_referee",
            ],
        )

    def test_pin_conflict_names_the_pinned_reason(self):
        detail = {
            "code": "pin_conflict",
            "club": 4,
            "rejected": {"4": "missing qualifications for head"},
        }
        self.assertEqual(
            explanations.suggestions(detail), ["change_pin", "qualify_roles"]
        )

    def test_attach_marks_every_issue(self):
        proposal = {
            "issue_details": [
                {"code": "participants_unresolved"},
                {"code": "preserved_conflict"},
            ]
        }
        explanations.attach_suggestions(proposal)
        self.assertEqual(
            [detail["suggestions"] for detail in proposal["issue_details"]],
            [["resolve_participants"], ["resolve_existing"]],
        )


class ExactSolverFallbackTest(unittest.TestCase):
    def test_unavailable_or_empty_inputs_keep_rows(self):
        rows = [duty(2, 1, T12, (3, 4))]
        result, report = exact.solve_season(rows, rows, targets={})
        self.assertEqual(clubs(result), [1])
        self.assertEqual(report["solver"], "local_search")
        self.assertEqual(report["solver_status"], "nothing_to_optimize")


@unittest.skipUnless(exact.exact_available(), "OR-Tools is not installed")
class ExactSolverTest(unittest.TestCase):
    def setUp(self):
        self.rows = [duty(2, 1, T12, (3, 4)), duty(3, 1, T14, (5, 6))]
        self.geometry = self.rows + GEOMETRY_EXTRA

    def solve(self, rows, **options):
        options.setdefault("season_minutes", {1: 600})
        options.setdefault("targets", {1: 300, 2: 300})
        return exact.solve_season(rows, self.geometry, **options)

    def test_optimizer_moves_duties_toward_targets(self):
        result, report = self.solve(self.rows)
        self.assertEqual(clubs(result), [2, 2])
        self.assertEqual(report["solver"], "exact")
        self.assertTrue(report["proven_optimal"])
        self.assertEqual(self.solve(self.rows), (result, report))

    def test_optimizer_respects_preserved_capacity(self):
        preserved = [dict(duty(2, 2, T12, (3, 4)), role="table")]
        result, _report = self.solve(
            self.rows,
            capacities={2: {"max_simultaneous": 1, "roles": ["table"]}},
            fixed_rows=preserved,
        )
        self.assertEqual(clubs(result), [1, 2])

    def test_optimizer_keeps_an_optimal_local_search_plan(self):
        local, _report = balance.rebalance_season(
            self.rows, self.geometry, season_minutes={1: 600}, targets={1: 300, 2: 300}
        )
        result, report = self.solve(local)
        self.assertEqual(clubs(result), clubs(local))
        self.assertEqual(report["solver_status"], "no_improvement")


if __name__ == "__main__":
    unittest.main()
