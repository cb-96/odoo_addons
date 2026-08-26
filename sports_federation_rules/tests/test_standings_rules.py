from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_legacy_rules")
class TestStandingsRules(TransactionCase):
    def setUp(self):
        super().setUp()
        self.engine = self.env["federation.standings.rules"]
        self.rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Rules",
                "points_win": 5,
                "points_draw": 2,
                "points_loss": -1,
            }
        )

    def test_explicit_points_override_defaults_including_zero(self):
        self.env["federation.points.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "result_type": "win",
                "points": 0,
            }
        )
        self.assertEqual(self.engine.points_map(self.rule_set)["win"], 0)
        self.assertEqual(self.engine.points_map(self.rule_set)["draw"], 2)
        self.assertEqual(self.engine.points_map(self.rule_set)["loss"], -1)

    def test_configured_tiebreak_order_and_reverse(self):
        self.env["federation.tie_break.rule"].create(
            [
                {
                    "rule_set_id": self.rule_set.id,
                    "sequence": 10,
                    "tie_break_type": "goals_against",
                    "reverse_order": True,
                },
                {
                    "rule_set_id": self.rule_set.id,
                    "sequence": 20,
                    "tie_break_type": "goals_scored",
                },
            ]
        )
        stats = {1: self.engine.initial_stats(), 2: self.engine.initial_stats()}
        stats[1].update(points=4, score_for=10, score_against=5)
        stats[2].update(points=4, score_for=8, score_against=3)
        ranked, notes = self.engine.rank(stats, self.rule_set, names={1: "A", 2: "B"})
        self.assertEqual([key for key, _row in ranked], [2, 1])
        self.assertIn("goals against", notes[1])

    def test_head_to_head_precedes_goal_difference(self):
        self.env["federation.tie_break.rule"].create(
            [
                {
                    "rule_set_id": self.rule_set.id,
                    "sequence": 10,
                    "tie_break_type": "head_to_head",
                },
                {
                    "rule_set_id": self.rule_set.id,
                    "sequence": 20,
                    "tie_break_type": "goal_difference",
                },
            ]
        )
        stats = {1: self.engine.initial_stats(), 2: self.engine.initial_stats()}
        stats[1].update(points=6, score_for=3, score_against=10)
        stats[2].update(points=6, score_for=20, score_against=1)
        ranked, _notes = self.engine.rank(
            stats, self.rule_set, matches=[(1, 2, 1, 0)], names={1: "A", 2: "B"}
        )
        self.assertEqual([key for key, _row in ranked], [1, 2])

    def test_locked_rule_set_protects_children(self):
        self.rule_set.action_lock()
        with self.assertRaises(Exception):
            self.env["federation.points.rule"].create(
                {
                    "rule_set_id": self.rule_set.id,
                    "result_type": "win",
                    "points": 7,
                }
            )
