from unittest.mock import MagicMock

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestAdvancedCompetitionEngine(TransactionCase):
    def test_double_elimination_route_counts(self):
        routes = self.env["federation.dynamic.pairing"].double_elimination_routes(8)
        self.assertEqual(routes["winner_bracket_matches"], 7)
        self.assertEqual(routes["loser_bracket_matches"], 6)
        self.assertEqual(routes["grand_final_matches"], 2)

    def test_double_elimination_rejects_non_power_of_two(self):
        with self.assertRaises(ValidationError):
            self.env["federation.dynamic.pairing"].double_elimination_routes(6)

    def test_ladder_challenge_distance(self):
        service = self.env["federation.dynamic.pairing"]
        self.assertTrue(service.ladder_challenge(5, 3, max_distance=3)["allowed"])
        with self.assertRaises(ValidationError):
            service.ladder_challenge(7, 2, max_distance=3)

    def test_swiss_pairing_avoids_previous_opponents(self):
        participants = MagicMock()
        participants.mapped.return_value.ids = [1, 2, 3, 4]
        result = self.env["federation.dynamic.pairing"].swiss_pairs(
            participants,
            previous_pairs=[(1, 2), (3, 4)],
            standings={1: 3, 2: 3, 3: 0, 4: 0},
        )
        self.assertNotIn(
            frozenset((1, 2)), {frozenset(pair) for pair in result["pairs"]}
        )
        self.assertNotIn(
            frozenset((3, 4)), {frozenset(pair) for pair in result["pairs"]}
        )

    def test_feasibility_covers_dynamic_formats(self):
        analyzer = self.env["federation.format.feasibility"]
        swiss = analyzer.estimate("swiss", 9, swiss_round_count=5)
        self.assertEqual((swiss["fixture_count"], swiss["round_count"]), (20, 5))
        double = analyzer.estimate("double_elimination", 8)
        self.assertEqual(double["fixture_count"], 15)
        ladder = analyzer.estimate("ladder", 12)
        self.assertTrue(ladder["feasible"])
        self.assertEqual(ladder["fixture_count"], 0)
