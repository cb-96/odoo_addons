from odoo.tests import TransactionCase
from odoo.exceptions import ValidationError


class TestRoundDateWizard(TransactionCase):
    """Tests for the federation.round.date.wizard."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "RDW Season",
                "date_start": "2025-09-01",
                "date_end": "2026-06-30",
            }
        )
        cls.club = cls.env["federation.club"].create({"name": "RDW Club"})
        cls.team1 = cls.env["federation.team"].create(
            {
                "name": "RDW Home",
                "club_id": cls.club.id,
            }
        )
        cls.team2 = cls.env["federation.team"].create(
            {
                "name": "RDW Away",
                "club_id": cls.club.id,
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "RDW Tournament",
                "season_id": cls.season.id,
                "date_start": "2025-10-01",
            }
        )
        cls.stage = cls.env["federation.tournament.stage"].create(
            {
                "name": "RDW Stage",
                "tournament_id": cls.tournament.id,
                "stage_type": "group",
                "date_start": "2025-10-01",
                "date_end": "2025-12-31",
            }
        )
        cls.round1 = cls.env["federation.tournament.round"].create(
            {
                "name": "Gameday 1",
                "stage_id": cls.stage.id,
                "sequence": 1,
            }
        )
        cls.round2 = cls.env["federation.tournament.round"].create(
            {
                "name": "Gameday 2",
                "stage_id": cls.stage.id,
                "sequence": 2,
            }
        )
        cls.match1 = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "stage_id": cls.stage.id,
                "round_id": cls.round1.id,
                "home_team_id": cls.team1.id,
                "away_team_id": cls.team2.id,
            }
        )
        cls.match2 = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "stage_id": cls.stage.id,
                "round_id": cls.round2.id,
                "home_team_id": cls.team2.id,
                "away_team_id": cls.team1.id,
            }
        )

    def test_wizard_sets_date_on_targeted_round(self):
        wiz = self.env["federation.round.date.wizard"].create(
            {
                "stage_id": self.stage.id,
                "round_id": self.round1.id,
                "date_scheduled": "2025-11-15 15:00:00",
            }
        )
        wiz.action_apply()
        self.assertTrue(self.match1.date_scheduled)
        self.assertIn("2025-11-15", str(self.match1.date_scheduled))

    def test_wizard_does_not_touch_other_rounds(self):
        wiz = self.env["federation.round.date.wizard"].create(
            {
                "stage_id": self.stage.id,
                "round_id": self.round1.id,
                "date_scheduled": "2025-11-15 15:00:00",
            }
        )
        wiz.action_apply()
        self.assertFalse(self.match2.date_scheduled)

    def test_date_before_stage_start_raises(self):
        with self.assertRaises(ValidationError):
            self.env["federation.round.date.wizard"].create(
                {
                    "stage_id": self.stage.id,
                    "round_id": self.round1.id,
                    "date_scheduled": "2025-09-15 15:00:00",  # before 2025-10-01
                }
            )

    def test_date_after_stage_end_raises(self):
        with self.assertRaises(ValidationError):
            self.env["federation.round.date.wizard"].create(
                {
                    "stage_id": self.stage.id,
                    "round_id": self.round1.id,
                    "date_scheduled": "2026-01-15 15:00:00",  # after 2025-12-31
                }
            )
