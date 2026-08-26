"""Foundation officiating tests: conflict detection, inline creation, batch wizard."""

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestPhase0MatchRefereeConflict(TransactionCase):
    """Conflict detection: same referee on overlapping matches."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        club = cls.env["federation.club"].create({"name": "P0 Club", "code": "P0C"})
        team_a = cls.env["federation.team"].create(
            {"name": "P0 Team A", "club_id": club.id, "code": "P0A"}
        )
        team_b = cls.env["federation.team"].create(
            {"name": "P0 Team B", "club_id": club.id, "code": "P0B"}
        )
        team_c = cls.env["federation.team"].create(
            {"name": "P0 Team C", "club_id": club.id, "code": "P0CC"}
        )
        season = cls.env["federation.season"].create(
            {
                "name": "P0 Season",
                "code": "P0S26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "P0 Tournament",
                "code": "P0T",
                "season_id": season.id,
                "date_start": "2026-06-01",
            }
        )
        cls.match_1 = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": team_a.id,
                "away_team_id": team_b.id,
                "date_scheduled": "2026-06-10 15:00:00",
            }
        )
        cls.match_2 = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": team_b.id,
                "away_team_id": team_c.id,
                "date_scheduled": "2026-06-10 15:00:00",
            }
        )
        cls.match_other_day = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": team_a.id,
                "away_team_id": team_c.id,
                "date_scheduled": "2026-06-11 15:00:00",
            }
        )
        cls.referee = cls.env["federation.referee"].create(
            {"name": "P0 Head Ref", "certification_level": "national"}
        )

    def test_conflict_same_day_raises(self):
        """Overlapping assignments stay draftable but cannot be confirmed together."""
        first_assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match_1.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        first_assignment.action_confirm()
        second_assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match_2.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        self.assertFalse(second_assignment.assignment_ready)
        with self.assertRaises(ValidationError):
            second_assignment.action_confirm()

    def test_different_day_allowed(self):
        """Assigning the same referee to matches on different days is allowed."""
        self.env["federation.match.referee"].create(
            {
                "match_id": self.match_1.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match_other_day.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        self.assertTrue(assignment.id)

    def test_cancelled_assignment_does_not_block(self):
        """A cancelled assignment does not trigger the conflict check."""
        first = self.env["federation.match.referee"].create(
            {
                "match_id": self.match_1.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        first.action_cancel()
        # Should succeed because the first assignment is cancelled
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match_2.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        self.assertTrue(assignment.id)

    def test_undated_match_no_conflict_check(self):
        """Assigning a referee to a match without a date never triggers the conflict check."""
        undated = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.match_1.home_team_id.id,
                "away_team_id": self.match_1.away_team_id.id,
            }
        )
        # Pre-existing assignment on a dated match
        self.env["federation.match.referee"].create(
            {
                "match_id": self.match_1.id,
                "referee_id": self.referee.id,
                "role": "assistant_1",
            }
        )
        # Should not raise even though referee has another assignment
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": undated.id,
                "referee_id": self.referee.id,
                "role": "assistant_1",
            }
        )
        self.assertTrue(assignment.id)


class TestPhase0InlineCreation(TransactionCase):
    """Inline assignment creation via referee_assignment_ids on federation.match."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        club = cls.env["federation.club"].create({"name": "IL Club", "code": "ILC"})
        team_a = cls.env["federation.team"].create(
            {"name": "IL Team A", "club_id": club.id, "code": "ILA"}
        )
        team_b = cls.env["federation.team"].create(
            {"name": "IL Team B", "club_id": club.id, "code": "ILB"}
        )
        season = cls.env["federation.season"].create(
            {
                "name": "IL Season",
                "code": "ILS26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        tournament = cls.env["federation.tournament"].create(
            {
                "name": "IL Tournament",
                "code": "ILT",
                "season_id": season.id,
                "date_start": "2026-06-01",
            }
        )
        cls.match = cls.env["federation.match"].create(
            {
                "tournament_id": tournament.id,
                "home_team_id": team_a.id,
                "away_team_id": team_b.id,
            }
        )
        cls.referee = cls.env["federation.referee"].create(
            {"name": "IL Referee", "certification_level": "regional"}
        )

    def test_inline_creation_via_one2many(self):
        """Assignments created via referee_assignment_ids on the match are correct."""
        self.match.write(
            {
                "referee_assignment_ids": [
                    (
                        0,
                        0,
                        {
                            "referee_id": self.referee.id,
                            "role": "head",
                        },
                    )
                ]
            }
        )
        self.assertEqual(self.match.referee_assignment_count, 1)
        assignment = self.match.referee_assignment_ids[0]
        self.assertEqual(assignment.referee_id, self.referee)
        self.assertEqual(assignment.role, "head")
        self.assertEqual(assignment.match_id, self.match)
