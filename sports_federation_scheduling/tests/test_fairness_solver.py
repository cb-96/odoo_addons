from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_fairness_solver")
class TestFairnessSolver(TransactionCase):
    def setUp(self):
        super().setUp()
        self.solver = self.env["federation.schedule.fairness.solver"]
        self.metrics = {
            "same_club_simultaneous_pairs": 2,
            "rest_shortfall_minutes": 10,
            "excess_consecutive_games": 1,
            "time_balance_spread": 5,
            "same_court_repeats": 3,
        }
        self.cfg = {
            "same_club_weight": 40,
            "rest_weight": 3,
            "consecutive_weight": 60,
            "time_balance_weight": 1,
            "court_balance_weight": 2,
        }

    def test_weighted_formula_reports_all_components(self):
        report = self.solver.score_metrics(self.metrics, self.cfg)
        self.assertEqual(report["weighted_score"], 181)
        self.assertEqual(
            report["components"],
            {
                "same_club": 80,
                "rest": 30,
                "consecutive": 60,
                "time_balance": 5,
                "court_balance": 6,
            },
        )

    def test_each_weight_changes_only_its_component(self):
        baseline = self.solver.score_metrics(self.metrics, self.cfg)
        for key, component in (
            ("same_club_weight", "same_club"),
            ("rest_weight", "rest"),
            ("consecutive_weight", "consecutive"),
            ("time_balance_weight", "time_balance"),
            ("court_balance_weight", "court_balance"),
        ):
            changed = dict(self.cfg)
            changed[key] += 1
            report = self.solver.score_metrics(self.metrics, changed)
            self.assertGreater(
                report["components"][component], baseline["components"][component]
            )
            for other in set(baseline["components"]) - {component}:
                self.assertEqual(
                    report["components"][other], baseline["components"][other]
                )

    def test_score_is_deterministic_and_does_not_mutate_inputs(self):
        metrics = dict(self.metrics)
        cfg = dict(self.cfg)
        first = self.solver.score_metrics(metrics, cfg)
        second = self.solver.score_metrics(metrics, cfg)
        self.assertEqual(first, second)
        self.assertEqual(metrics, self.metrics)
        self.assertEqual(cfg, self.cfg)
