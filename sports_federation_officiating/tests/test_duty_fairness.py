from odoo.tests.common import TransactionCase
from odoo.tests import tagged

from odoo.addons.sports_federation_officiating import duty_fairness


@tagged("post_install", "-at_install", "sf_officiating")
class TestClubDutySeasonFairness(TransactionCase):
    """Pure-logic guards for the season-fairness refinement layer."""

    def _rows(self, n, club=1):
        return [
            {"fixture": i, "club": club, "start": "2026-11-17 10:00:00",
             "end": "2026-11-17 11:00:00", "duration_minutes": 60,
             "roles": ["table"], "opponents": [9, 8]}
            for i in range(n)
        ]

    def test_rebalance_respects_capacity_and_reduces_deviation(self):
        rows = self._rows(6)
        caps = {c: {"max_simultaneous": 1, "roles": ["table"]} for c in (1, 2, 3)}
        targets = {1: 120, 2: 120, 3: 120}
        base = duty_fairness.quadratic_objective(
            {r["fixture"]: 1 for r in rows}, {r["fixture"]: r for r in rows}, {}, targets
        )
        assign, report = duty_fairness.rebalance_quadratic(rows, caps, targets=targets, seed=1)
        self.assertLessEqual(report["objective"], base)
        by = {r["fixture"]: r for r in rows}
        for club in set(assign.values()):
            self.assertTrue(duty_fairness.concurrency_ok(assign, by, club, 1))

    def test_pin_is_immovable(self):
        rows = self._rows(1)
        assign, _ = duty_fairness.rebalance_quadratic(
            rows, {c: {"max_simultaneous": 2, "roles": ["table"]} for c in (1, 2)},
            pins={0: 1}, targets={1: 0, 2: 120}, seed=3,
        )
        self.assertEqual(assign[0], 1)
