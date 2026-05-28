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

    def test_duplicate_same_category_pairing_rejected_in_same_round(self):
        """Test that duplicate same category pairing rejected in same round."""
        round_record = self._create_round(1)
        self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.group_stage.id,
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "round_id": round_record.id,
                "state": "draft",
            }
        )

        with self.assertRaises(ValidationError):
            self.env["federation.match"].create(
                {
                    "tournament_id": self.tournament.id,
                    "stage_id": self.group_stage.id,
                    "home_team_id": self.team_b.id,
                    "away_team_id": self.team_a.id,
                    "round_id": round_record.id,
                    "state": "draft",
                }
            )

    def test_same_pairing_in_different_rounds_allowed(self):
        """Test that same pairing in different rounds allowed."""
        round_one = self._create_round(1)
        round_two = self._create_round(2)

        first_match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.group_stage.id,
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "round_id": round_one.id,
                "state": "draft",
            }
        )
        second_match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.group_stage.id,
                "home_team_id": self.team_b.id,
                "away_team_id": self.team_a.id,
                "round_id": round_two.id,
                "state": "draft",
            }
        )

        self.assertTrue(first_match.id)
        self.assertTrue(second_match.id)

    def test_round_date_write_preserves_match_time_components(self):
        """Test that round date write preserves match time components."""
        round_record = self._create_round(1)
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.group_stage.id,
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "round_id": round_record.id,
                "date_scheduled": datetime(2024, 10, 1, 19, 30),
                "state": "draft",
            }
        )

        round_record.write({"round_date": "2024-10-05"})

        scheduled_dt = fields.Datetime.to_datetime(match.date_scheduled)
        self.assertEqual(str(scheduled_dt.date()), "2024-10-05")
        self.assertEqual((scheduled_dt.hour, scheduled_dt.minute), (19, 30))

    def test_round_date_write_keeps_midnight_matches(self):
        """Test that round date write keeps midnight matches."""
        round_record = self._create_round(1, round_date="2024-10-01")
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.group_stage.id,
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "round_id": round_record.id,
                "scheduled_time": 0.0,
                "state": "draft",
            }
        )

        round_record.write({"round_date": "2024-10-05"})

        scheduled_dt = fields.Datetime.to_datetime(match.date_scheduled)
        self.assertEqual(str(scheduled_dt.date()), "2024-10-05")
        self.assertEqual((scheduled_dt.hour, scheduled_dt.minute), (0, 0))

    def test_schedule_by_round_creates_rounds_with_dates_and_venue(self):
        """Matches are scheduled using dates from pre-defined gamedays."""
        if not self.env.get("federation.round.robin.service"):
            self.skipTest("sports_federation_competition_engine not installed.")

        self.tournament.state = "open"
        participants = self._create_participants(
            [
                self.team_a,
                self.team_b,
                self.team_c,
                self.team_d,
            ]
        )
        service = self.env["federation.round.robin.service"]
        start_dt = datetime(2024, 11, 1, 9, 0)

        # Pre-create 3 gamedays with dates and venue (4 teams → 3 algorithm rounds)
        existing_rounds = self.env["federation.tournament.round"]
        for i, round_date in enumerate(
            [
                datetime(2024, 11, 1).date(),
                datetime(2024, 11, 2).date(),
                datetime(2024, 11, 3).date(),
            ],
            start=1,
        ):
            existing_rounds |= self._create_round(
                i, round_date=round_date, venue=self.venue
            )

        matches = service.generate(
            tournament=self.tournament,
            stage=self.group_stage,
            participants=participants,
            options={
                "double_round": False,
                "schedule_by_round": True,
                "start_datetime": start_dt,
                "round_interval_hours": 24,
                "interval_hours": 2,
                "venue": self.venue.name,
                "overwrite": True,
            },
        )

        rounds = self.group_stage.round_ids.sorted("sequence")
        self.assertEqual(len(matches), 6)
        self.assertEqual(rounds.ids, existing_rounds.ids)
        self.assertEqual(
            rounds.mapped("round_date"),
            [
                datetime(2024, 11, 1).date(),
                datetime(2024, 11, 2).date(),
                datetime(2024, 11, 3).date(),
            ],
        )
        self.assertTrue(
            all(round_record.venue_id == self.venue for round_record in rounds)
        )
        self.assertEqual(
            [
                len(
                    matches.filtered(
                        lambda match, round_record=round_record: match.round_id
                        == round_record
                    )
                )
                for round_record in rounds
            ],
            [2, 2, 2],
        )

    def test_round_robin_wizard_reuses_existing_stage_rounds(self):
        """Test that round robin wizard reuses existing stage rounds."""
        if not self.env.get("federation.round.robin.wizard"):
            self.skipTest("sports_federation_competition_engine not installed.")

        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Round Wizard Rule Set",
                "code": "RWRS",
            }
        )
        self.tournament.rule_set_id = rule_set.id
        self.tournament.state = "open"
        self._create_participants(
            [
                self.team_a,
                self.team_b,
                self.team_c,
                self.team_d,
            ]
        )

        existing_rounds = self.env["federation.tournament.round"]
        for sequence, round_date in enumerate(
            ["2024-12-01", "2024-12-08", "2024-12-15"], start=1
        ):
            existing_rounds |= self._create_round(
                sequence, round_date=round_date, venue=self.venue
            )

        wizard = self.env["federation.round.robin.wizard"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.group_stage.id,
                "use_all_participants": True,
                "round_type": "single",
                "rounds_count": 1,
                "schedule_by_round": True,
                "start_datetime": datetime(2024, 12, 1, 9, 0),
                "interval_hours": 2,
                "overwrite": True,
            }
        )

        wizard.action_generate()

        matches = self.env["federation.match"].search(
            [
                ("tournament_id", "=", self.tournament.id),
                ("stage_id", "=", self.group_stage.id),
            ],
            order="round_number asc, date_scheduled asc, id asc",
        )
        self.assertEqual(len(matches), 6)
        self.assertEqual(matches.mapped("round_id").ids, existing_rounds.ids)
        self.assertTrue(all(match.venue_id == self.venue for match in matches))

        expected_datetimes = [
            [datetime(2024, 12, 1, 9, 0), datetime(2024, 12, 1, 11, 0)],
            [datetime(2024, 12, 8, 9, 0), datetime(2024, 12, 8, 11, 0)],
            [datetime(2024, 12, 15, 9, 0), datetime(2024, 12, 15, 11, 0)],
        ]
        for round_record, expected in zip(existing_rounds, expected_datetimes):
            round_matches = matches.filtered(
                lambda match, round_record=round_record: match.round_id == round_record
            )
            self.assertEqual(len(round_matches), 2)
            self.assertEqual(round_matches.mapped("date_scheduled"), expected)
