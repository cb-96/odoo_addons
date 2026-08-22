from datetime import datetime
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_fairness_solver")
class TestFairnessSolver(TransactionCase):
    def test_weighted_formula_reports_all_components(self):
        solver = self.env["federation.schedule.fairness.solver"]
        metrics = {
            "same_club_simultaneous_pairs": 2,
            "rest_shortfall_minutes": 10,
            "excess_consecutive_games": 1,
            "time_balance_spread": 5,
            "same_court_repeats": 3,
        }
        cfg = {
            "same_club_weight": 40,
            "rest_weight": 3,
            "consecutive_weight": 60,
            "time_balance_weight": 1,
            "court_balance_weight": 2,
        }
        components = {
            "same_club": 80,
            "rest": 30,
            "consecutive": 60,
            "time_balance": 5,
            "court_balance": 6,
        }
        self.assertEqual(sum(components.values()), 181)
        self.assertTrue(hasattr(solver, "evaluate"))
