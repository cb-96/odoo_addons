from odoo.tests import TransactionCase


class TestFormatFeasibility(TransactionCase):
    def test_common_formats_have_deterministic_counts(self):
        analyzer = self.env["federation.format.feasibility"]
        self.assertEqual(
            (
                analyzer.estimate("single_round_robin", 6)["fixture_count"],
                analyzer.estimate("single_round_robin", 6)["round_count"],
            ),
            (15, 5),
        )
        self.assertEqual(
            (
                analyzer.estimate("double_round_robin", 6)["fixture_count"],
                analyzer.estimate("double_round_robin", 6)["round_count"],
            ),
            (30, 10),
        )
        knockout = analyzer.estimate("knockout", 8, series_length=3)
        self.assertEqual((knockout["fixture_count"], knockout["round_count"]), (21, 9))

    def test_pool_knockout_handles_uneven_pool_sizes(self):
        result = self.env["federation.format.feasibility"].estimate(
            "pool_knockout", 10, pool_count=3
        )
        self.assertTrue(result["feasible"])
        self.assertEqual((result["fixture_count"], result["round_count"]), (17, 6))

    def test_impossible_formats_explain_failure(self):
        analyzer = self.env["federation.format.feasibility"]
        self.assertFalse(
            analyzer.estimate("pool_knockout", 6, pool_count=4)["feasible"]
        )
        self.assertFalse(analyzer.estimate("split_pools", 5)["feasible"])
        self.assertFalse(analyzer.estimate("custom", 8)["feasible"])
