from datetime import datetime

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestRoundSchedule(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Round Test Club",
                "code": "RTC",
            }
        )
        cls.venue = cls.env["federation.venue"].create(
            {
                "name": "Round Arena",
                "city": "Test City",
            }
        )
        cls.venue2 = cls.env["federation.venue"].create(
            {
                "name": "Backup Arena",
                "city": "Other City",
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "Round Team A",
                "club_id": cls.club.id,
                "code": "RTA",
                "category": "senior",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "Round Team B",
                "club_id": cls.club.id,
                "code": "RTB",
                "category": "senior",
            }
        )
        cls.team_c = cls.env["federation.team"].create(
            {
                "name": "Round Team C",
                "club_id": cls.club.id,
                "code": "RTC1",
                "category": "senior",
            }
        )
        cls.team_d = cls.env["federation.team"].create(
            {
                "name": "Round Team D",
                "club_id": cls.club.id,
                "code": "RTD",
                "category": "senior",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Round Season",
                "code": "RSEASON",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Round Tournament",
                "code": "RTOUR",
                "season_id": cls.season.id,
                "date_start": "2024-06-01",
            }
        )
        cls.group_stage = cls.env["federation.tournament.stage"].create(
            {
                "name": "Round Group Stage",
                "tournament_id": cls.tournament.id,
                "stage_type": "group",
            }
        )

    def _create_round(
        self, sequence, round_date=False, venue=False, stage=False, group=False
    ):
        """Exercise create round."""
        vals = {
            "stage_id": (stage or self.group_stage).id,
            "sequence": sequence,
        }
        if round_date:
            vals["round_date"] = round_date
        if venue:
            vals["venue_id"] = venue.id
        if group:
            vals["group_id"] = group.id
        return self.env["federation.tournament.round"].create(vals)

    def _create_participants(self, teams, stage=False):
        """Exercise create participants."""
        participants = self.env["federation.tournament.participant"]
        for index, team in enumerate(teams, start=1):
            participants |= self.env["federation.tournament.participant"].create(
                {
                    "tournament_id": self.tournament.id,
                    "stage_id": (stage or self.group_stage).id,
                    "team_id": team.id,
                    "state": "confirmed",
                    "seed": index,
                }
            )
        return participants

    def test_match_round_assignment_inherits_scope_and_venue(self):
        """Test that match round assignment inherits scope and venue."""
        round_record = self._create_round(1, round_date="2024-09-15", venue=self.venue)

        match = self.env["federation.match"].create(
            {
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "round_id": round_record.id,
                "state": "draft",
            }
        )

        self.assertEqual(match.tournament_id, self.tournament)
        self.assertEqual(match.stage_id, self.group_stage)
        self.assertEqual(match.venue_id, self.venue)
        self.assertEqual(match.scheduled_date, fields.Date.to_date("2024-09-15"))

    def test_match_scheduled_time_write_uses_round_date_even_at_midnight(self):
        """Test that match scheduled time write uses round date even at midnight."""
        round_record = self._create_round(1, round_date="2024-09-15")
        match = self.env["federation.match"].create(
            {
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "round_id": round_record.id,
                "state": "draft",
            }
        )

        match.write({"scheduled_time": 0.0})

        scheduled_dt = fields.Datetime.to_datetime(match.date_scheduled)
        self.assertEqual(str(scheduled_dt.date()), "2024-09-15")
        self.assertEqual((scheduled_dt.hour, scheduled_dt.minute), (0, 0))
        self.assertEqual(match.scheduled_time, 0.0)

    def test_match_datetime_write_is_normalized_to_round_date(self):
        """Test that match datetime write is normalized to round date."""
        round_record = self._create_round(1, round_date="2024-09-15")
        match = self.env["federation.match"].create(
            {
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "round_id": round_record.id,
                "state": "draft",
            }
        )

        match.write({"date_scheduled": datetime(2024, 9, 20, 18, 45)})

        scheduled_dt = fields.Datetime.to_datetime(match.date_scheduled)
        self.assertEqual(str(scheduled_dt.date()), "2024-09-15")
        self.assertEqual((scheduled_dt.hour, scheduled_dt.minute), (18, 45))
        self.assertAlmostEqual(match.scheduled_time, 18.75, places=2)

    def test_match_round_rejects_conflicting_venue(self):
        """Test that match round rejects conflicting venue."""
        round_record = self._create_round(1, venue=self.venue)

        with self.assertRaises(ValidationError):
            self.env["federation.match"].create(
                {
                    "tournament_id": self.tournament.id,
                    "stage_id": self.group_stage.id,
                    "home_team_id": self.team_a.id,
                    "away_team_id": self.team_b.id,
                    "round_id": round_record.id,
                    "venue_id": self.venue2.id,
                    "state": "draft",
                }
            )
