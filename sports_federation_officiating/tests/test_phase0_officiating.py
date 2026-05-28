"""Phase 0 officiating tests: conflict detection, inline creation, batch wizard."""

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


class TestPhase0BatchWizard(TransactionCase):
    """Batch round-assign wizard creates correct assignment records."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        club = cls.env["federation.club"].create({"name": "BW Club", "code": "BWC"})
        teams = [
            cls.env["federation.team"].create(
                {"name": f"BW Team {i}", "club_id": club.id, "code": f"BW{i}"}
            )
            for i in range(1, 5)
        ]
        season = cls.env["federation.season"].create(
            {
                "name": "BW Season",
                "code": "BWS26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        tournament = cls.env["federation.tournament"].create(
            {
                "name": "BW Tournament",
                "code": "BWT",
                "season_id": season.id,
                "date_start": "2026-06-01",
            }
        )
        stage = cls.env["federation.tournament.stage"].create(
            {
                "name": "BW Stage",
                "tournament_id": tournament.id,
                "stage_type": "group",
                "sequence": 1,
            }
        )
        cls.round = cls.env["federation.tournament.round"].create(
            {"name": "BW Round 1", "stage_id": stage.id}
        )
        # 4 matches in the round (round-robin style, unique pairings)
        cls.matches = cls.env["federation.match"].browse()
        for i in range(4):
            m = cls.env["federation.match"].create(
                {
                    "tournament_id": tournament.id,
                    "round_id": cls.round.id,
                    "home_team_id": teams[i % 4].id,
                    "away_team_id": teams[(i + 1) % 4].id,
                }
            )
            cls.matches |= m
        cls.referee = cls.env["federation.referee"].create(
            {"name": "BW Table Official", "certification_level": "local"}
        )

    def test_wizard_creates_all_assignments(self):
        """Wizard creates one assignment per match for the chosen role."""
        wizard = self.env["federation.round.assign.wizard"].create(
            {
                "round_id": self.round.id,
                "role": "table",
                "referee_id": self.referee.id,
            }
        )
        self.assertEqual(wizard.matches_total, 4)
        self.assertEqual(wizard.matches_to_assign, 4)
        self.assertEqual(wizard.matches_skipped, 0)

        wizard.action_apply()

        assignments = self.env["federation.match.referee"].search(
            [
                ("match_id", "in", self.matches.ids),
                ("role", "=", "table"),
                ("referee_id", "=", self.referee.id),
                ("state", "!=", "cancelled"),
            ]
        )
        self.assertEqual(len(assignments), 4)

    def test_wizard_skips_already_assigned_roles(self):
        """Wizard skips matches that already have an active assignment for the role."""
        first_match = self.matches[0]
        extra_ref = self.env["federation.referee"].create({"name": "BW Head Ref"})
        # Pre-assign head on first match
        self.env["federation.match.referee"].create(
            {
                "match_id": first_match.id,
                "referee_id": extra_ref.id,
                "role": "head",
            }
        )
        wizard = self.env["federation.round.assign.wizard"].create(
            {
                "round_id": self.round.id,
                "role": "head",
                "referee_id": self.referee.id,
            }
        )
        # Preview: 1 skipped, 3 to assign
        self.assertEqual(wizard.matches_skipped, 1)
        self.assertEqual(wizard.matches_to_assign, 3)

        wizard.action_apply()

        # Only 3 new ones created for self.referee; the first match keeps extra_ref
        new_assignments = self.env["federation.match.referee"].search(
            [
                ("match_id", "in", self.matches.ids),
                ("role", "=", "head"),
                ("referee_id", "=", self.referee.id),
            ]
        )
        self.assertEqual(len(new_assignments), 3)
        # The pre-existing assignment on first_match is untouched
        existing = self.env["federation.match.referee"].search(
            [
                ("match_id", "=", first_match.id),
                ("role", "=", "head"),
                ("state", "!=", "cancelled"),
            ]
        )
        self.assertEqual(len(existing), 1)
        self.assertEqual(existing.referee_id, extra_ref)

    def test_wizard_empty_round_no_crash(self):
        """Wizard on a round with no matches completes without error."""
        stage = self.round.stage_id
        empty_round = self.env["federation.tournament.round"].create(
            {"name": "Empty Round", "stage_id": stage.id, "sequence": 99}
        )
        wizard = self.env["federation.round.assign.wizard"].create(
            {
                "round_id": empty_round.id,
                "role": "head",
                "referee_id": self.referee.id,
            }
        )
        self.assertEqual(wizard.matches_to_assign, 0)
        result = wizard.action_apply()
        self.assertEqual(result["type"], "ir.actions.act_window_close")
