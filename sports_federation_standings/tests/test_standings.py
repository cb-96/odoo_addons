from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestStandings(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.has_result_control = (
            "include_in_official_standings" in cls.env["federation.match"]._fields
        )
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Test Club",
                "code": "TEST",
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "Team A",
                "club_id": cls.club.id,
                "code": "TA",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "Team B",
                "club_id": cls.club.id,
                "code": "TB",
            }
        )
        cls.team_c = cls.env["federation.team"].create(
            {
                "name": "Team C",
                "club_id": cls.club.id,
                "code": "TC",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Test Season",
                "code": "TS2024",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Test Tournament",
                "code": "TTOUR",
                "season_id": cls.season.id,
                "date_start": "2024-06-01",
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Test Rule Set",
                "code": "TRS",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        # Create participants
        cls.participant_a = cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_a.id,
            }
        )
        cls.participant_b = cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_b.id,
            }
        )
        cls.participant_c = cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_c.id,
            }
        )

    def _match_vals(self, vals):
        """Add include_in_official_standings=True when result_control is installed."""
        if self.has_result_control:
            vals.setdefault("include_in_official_standings", True)
        return vals

    def test_recompute_two_team_standing(self):
        """Test standings computation with two teams."""
        # Create match: Team A beats Team B 2-1
        self.env["federation.match"].create(
            self._match_vals(
                {
                    "tournament_id": self.tournament.id,
                    "home_team_id": self.team_a.id,
                    "away_team_id": self.team_b.id,
                    "home_score": 2,
                    "away_score": 1,
                    "state": "done",
                }
            )
        )

        standing = self.env["federation.standing"].create(
            {
                "name": "Test Standing",
                "tournament_id": self.tournament.id,
                "rule_set_id": self.rule_set.id,
            }
        )
        standing.action_recompute()

        # All 3 tournament participants should have standing lines
        self.assertEqual(len(standing.line_ids), 3)

        # Team A should be first (3 points, 1 win)
        line_a = standing.line_ids.filtered(
            lambda ln: ln.participant_id == self.participant_a
        )
        self.assertEqual(line_a.rank, 1)
        self.assertEqual(line_a.played, 1)
        self.assertEqual(line_a.won, 1)
        self.assertEqual(line_a.drawn, 0)
        self.assertEqual(line_a.lost, 0)
        self.assertEqual(line_a.score_for, 2)
        self.assertEqual(line_a.score_against, 1)
        self.assertEqual(line_a.score_diff, 1)
        self.assertEqual(line_a.points, 3)

        # Team B should be last (0 points, 1 loss, worst goal diff)
        line_b = standing.line_ids.filtered(
            lambda ln: ln.participant_id == self.participant_b
        )
        self.assertEqual(line_b.rank, 3)
        self.assertEqual(line_b.played, 1)
        self.assertEqual(line_b.won, 0)
        self.assertEqual(line_b.drawn, 0)
        self.assertEqual(line_b.lost, 1)
        self.assertEqual(line_b.score_for, 1)
        self.assertEqual(line_b.score_against, 2)
        self.assertEqual(line_b.score_diff, -1)
        self.assertEqual(line_b.points, 0)

    def test_recompute_three_team_standing(self):
        """Test standings computation with three teams."""
        # Match 1: A beats B 2-1
        self.env["federation.match"].create(
            self._match_vals(
                {
                    "tournament_id": self.tournament.id,
                    "home_team_id": self.team_a.id,
                    "away_team_id": self.team_b.id,
                    "home_score": 2,
                    "away_score": 1,
                    "state": "done",
                }
            )
        )
        # Match 2: B beats C 3-0
        self.env["federation.match"].create(
            self._match_vals(
                {
                    "tournament_id": self.tournament.id,
                    "home_team_id": self.team_b.id,
                    "away_team_id": self.team_c.id,
                    "home_score": 3,
                    "away_score": 0,
                    "state": "done",
                }
            )
        )
        # Match 3: A draws C 1-1
        self.env["federation.match"].create(
            self._match_vals(
                {
                    "tournament_id": self.tournament.id,
                    "home_team_id": self.team_a.id,
                    "away_team_id": self.team_c.id,
                    "home_score": 1,
                    "away_score": 1,
                    "state": "done",
                }
            )
        )

        standing = self.env["federation.standing"].create(
            {
                "name": "Test Standing",
                "tournament_id": self.tournament.id,
                "rule_set_id": self.rule_set.id,
            }
        )
        standing.action_recompute()

        self.assertEqual(len(standing.line_ids), 3)

        # Team A: 1 win, 1 draw = 4 points
        line_a = standing.line_ids.filtered(
            lambda ln: ln.participant_id == self.participant_a
        )
        self.assertEqual(line_a.rank, 1)
        self.assertEqual(line_a.played, 2)
        self.assertEqual(line_a.won, 1)
        self.assertEqual(line_a.drawn, 1)
        self.assertEqual(line_a.lost, 0)
        self.assertEqual(line_a.points, 4)

        # Team B: 1 win, 1 loss = 3 points
        line_b = standing.line_ids.filtered(
            lambda ln: ln.participant_id == self.participant_b
        )
        self.assertEqual(line_b.rank, 2)
        self.assertEqual(line_b.played, 2)
        self.assertEqual(line_b.won, 1)
        self.assertEqual(line_b.drawn, 0)
        self.assertEqual(line_b.lost, 1)
        self.assertEqual(line_b.points, 3)

        # Team C: 1 draw, 1 loss = 1 point
        line_c = standing.line_ids.filtered(
            lambda ln: ln.participant_id == self.participant_c
        )
        self.assertEqual(line_c.rank, 3)
        self.assertEqual(line_c.played, 2)
        self.assertEqual(line_c.won, 0)
        self.assertEqual(line_c.drawn, 1)
        self.assertEqual(line_c.lost, 1)
        self.assertEqual(line_c.points, 1)

    def test_score_diff_computation(self):
        """Test score difference computation."""
        # Create match with large score difference
        self.env["federation.match"].create(
            self._match_vals(
                {
                    "tournament_id": self.tournament.id,
                    "home_team_id": self.team_a.id,
                    "away_team_id": self.team_b.id,
                    "home_score": 5,
                    "away_score": 0,
                    "state": "done",
                }
            )
        )

        standing = self.env["federation.standing"].create(
            {
                "name": "Test Standing",
                "tournament_id": self.tournament.id,
                "rule_set_id": self.rule_set.id,
            }
        )
        standing.action_recompute()

        line_a = standing.line_ids.filtered(
            lambda ln: ln.participant_id == self.participant_a
        )
        self.assertEqual(line_a.score_diff, 5)

        line_b = standing.line_ids.filtered(
            lambda ln: ln.participant_id == self.participant_b
        )
        self.assertEqual(line_b.score_diff, -5)

    def test_group_stage_consistency_constraint(self):
        """Test that group must belong to stage."""
        stage = self.env["federation.tournament.stage"].create(
            {
                "name": "Group Stage",
                "tournament_id": self.tournament.id,
            }
        )
        other_stage = self.env["federation.tournament.stage"].create(
            {
                "name": "Other Stage",
                "tournament_id": self.tournament.id,
            }
        )
        group = self.env["federation.tournament.group"].create(
            {
                "name": "Group A",
                "stage_id": stage.id,
            }
        )

        # This should work
        standing = self.env["federation.standing"].create(
            {
                "name": "Test Standing",
                "tournament_id": self.tournament.id,
                "stage_id": stage.id,
                "group_id": group.id,
            }
        )
        self.assertTrue(standing.id)

        # This should fail - group doesn't belong to stage
        with self.assertRaises(ValidationError):
            self.env["federation.standing"].create(
                {
                    "name": "Bad Standing",
                    "tournament_id": self.tournament.id,
                    "stage_id": other_stage.id,
                    "group_id": group.id,
                }
            )

    def test_frozen_standing_blocks_recompute(self):
        """Test that frozen standing blocks recomputation."""
        standing = self.env["federation.standing"].create(
            {
                "name": "Test Standing",
                "tournament_id": self.tournament.id,
                "rule_set_id": self.rule_set.id,
            }
        )
        standing.action_recompute()
        standing.action_freeze()

        self.assertEqual(standing.state, "frozen")

        # Should raise error without force_recompute
        with self.assertRaises(ValidationError):
            standing.action_recompute()

        # Should work with force_recompute
        standing.with_context(force_recompute=True).action_recompute()
        self.assertEqual(standing.state, "computed")

    def test_unique_participant_per_standing(self):
        """Test that participant can only appear once per standing."""
        standing = self.env["federation.standing"].create(
            {
                "name": "Test Standing",
                "tournament_id": self.tournament.id,
                "rule_set_id": self.rule_set.id,
            }
        )

        # Create first line
        self.env["federation.standing.line"].create(
            {
                "standing_id": standing.id,
                "participant_id": self.participant_a.id,
            }
        )

        # Try to create duplicate - should fail
        with self.assertRaises(Exception):
            self.env["federation.standing.line"].create(
                {
                    "standing_id": standing.id,
                    "participant_id": self.participant_a.id,
                }
            )

    def test_standing_model_order(self):
        """Test that FederationStanding uses the expected composite _order."""
        self.assertEqual(
            self.env["federation.standing"]._order,
            "tournament_id, stage_id, group_id, name",
        )
