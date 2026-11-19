from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.sports_federation_officiating import duty_fairness

SLOTS = (
    ("2026-11-17 10:00:00", "2026-11-17 11:00:00"),
    ("2026-11-17 12:00:00", "2026-11-17 13:00:00"),
)


@tagged("post_install", "-at_install", "sf_officiating")
class TestClubDutySeasonFairness(TransactionCase):
    """Pure-logic guards for the season-fairness refinement layer."""

    def _rows(self, n, club=1, slots=SLOTS):
        rows = []
        for i in range(n):
            start, end = slots[i % len(slots)]
            rows.append(
                {
                    "fixture": i,
                    "club": club,
                    "start": start,
                    "end": end,
                    "duration_minutes": 60,
                    "roles": ["table"],
                    "opponents": [9, 8],
                }
            )
        return rows

    def test_rebalance_respects_capacity_and_reduces_deviation(self):
        # Six duties over two slots, three clubs that each staff one at a time:
        # the only capacity-feasible plan gives every club one duty per slot.
        rows = self._rows(6)
        caps = {c: {"max_simultaneous": 1, "roles": ["table"]} for c in (1, 2, 3)}
        targets = {1: 120, 2: 120, 3: 120}
        by = {r["fixture"]: r for r in rows}
        base = duty_fairness.quadratic_objective(
            {r["fixture"]: 1 for r in rows}, by, {}, targets
        )
        assign, report = duty_fairness.rebalance_quadratic(
            rows, caps, targets=targets, seed=1
        )
        self.assertEqual(report["overload"], 0)
        self.assertLessEqual(report["objective"], base)
        for club in set(assign.values()):
            self.assertTrue(duty_fairness.concurrency_ok(assign, by, club, 1))

    def test_infeasible_instance_reports_overload(self):
        # Six simultaneous duties cannot fit three clubs of capacity one.
        rows = self._rows(6, slots=SLOTS[:1])
        caps = {c: {"max_simultaneous": 1, "roles": ["table"]} for c in (1, 2, 3)}
        _assign, report = duty_fairness.rebalance_quadratic(
            rows, caps, targets={1: 120, 2: 120, 3: 120}, seed=1
        )
        self.assertGreater(report["overload"], 0)

    def test_pin_is_immovable(self):
        rows = self._rows(1)
        assign, _ = duty_fairness.rebalance_quadratic(
            rows,
            {c: {"max_simultaneous": 2, "roles": ["table"]} for c in (1, 2)},
            pins={0: 1},
            targets={1: 0, 2: 120},
            seed=3,
        )
        self.assertEqual(assign[0], 1)
