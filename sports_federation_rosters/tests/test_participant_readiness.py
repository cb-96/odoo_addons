from datetime import date, timedelta

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestParticipantReadiness(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.today = date.today()
        cls.season_start = cls.today - timedelta(days=30)
        cls.season_end = cls.today + timedelta(days=365)
        cls.tournament_start = cls.today + timedelta(days=30)
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Participant Ready Club",
                "code": "PRC1",
            }
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Participant Ready Team",
                "club_id": cls.club.id,
                "code": "PRT1",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Participant Ready Season",
                "code": "PRS1",
                "date_start": cls.season_start.isoformat(),
                "date_end": cls.season_end.isoformat(),
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Participant Ready Rules",
                "code": "PRR1",
                "squad_min_size": 1,
            }
        )
        cls.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": cls.rule_set.id,
                "name": "Active License Required",
                "eligibility_type": "license_valid",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Participant Ready Tournament",
                "code": "PRT-TOUR",
                "season_id": cls.season.id,
                "date_start": cls.tournament_start.isoformat(),
                "rule_set_id": cls.rule_set.id,
            }
        )
        cls.player = cls.env["federation.player"].create(
            {
                "first_name": "Eligible",
                "last_name": "Player",
                "gender": "male",
            }
        )
        cls.opponent_team = cls.env["federation.team"].create(
            {
                "name": "Participant Opponent Team",
                "club_id": cls.club.id,
                "code": "PRT2",
            }
        )
        cls.opponent_player = cls.env["federation.player"].create(
            {
                "first_name": "Opponent",
                "last_name": "Player",
                "gender": "male",
            }
        )

    def _create_ready_roster(self, team, player, name):
        """Exercise create ready roster."""
        roster = self.env["federation.team.roster"].create(
            {
                "name": name,
                "team_id": team.id,
                "season_id": self.season.id,
                "rule_set_id": self.rule_set.id,
            }
        )
        license_record = self.env["federation.player.license"].create(
            {
                "name": f"LIC-{name.upper().replace(' ', '-')}",
                "player_id": player.id,
                "season_id": self.season.id,
                "club_id": self.club.id,
                "issue_date": self.season_start.isoformat(),
                "expiry_date": (self.season_end + timedelta(days=365)).isoformat(),
                "state": "active",
            }
        )
        self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": player.id,
                "license_id": license_record.id,
            }
        )
        roster.action_activate()
        return roster

    def test_participant_confirm_allows_missing_roster_before_deadline(self):
        """Test that participant confirm allows missing roster before deadline."""
        participant = self.env["federation.tournament.participant"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": self.team.id,
            }
        )

        self.assertTrue(participant.readiness_roster_id)
        self.assertEqual(participant.readiness_roster_id.status, "draft")
        self.assertTrue(participant.ready_for_confirmation)
        self.assertTrue(participant.roster_deadline_date)
        self.assertIn(
            "must have an active ready roster by", participant.confirmation_feedback
        )

        participant.action_confirm()

        self.assertEqual(participant.state, "confirmed")

    def test_participant_confirm_blocks_missing_roster_once_deadline_reached(self):
        """Test that participant confirm blocks once the roster deadline is reached."""
        urgent_tournament = self.env["federation.tournament"].create(
            {
                "name": "Participant Deadline Tournament",
                "code": "PRT-DEADLINE",
                "season_id": self.season.id,
                "date_start": (self.today + timedelta(days=7)).isoformat(),
                "rule_set_id": self.rule_set.id,
            }
        )
        participant = self.env["federation.tournament.participant"].create(
            {
                "tournament_id": urgent_tournament.id,
                "team_id": self.team.id,
            }
        )

        self.assertFalse(participant.ready_for_confirmation)
        self.assertIn("Roster deadline reached", participant.confirmation_feedback)
        self.assertTrue(participant.readiness_roster_id)

        with self.assertRaisesRegex(
            ValidationError,
            "Participants cannot be confirmed after the roster deadline",
        ):
            participant.action_confirm()

        self.assertEqual(participant.state, "registered")

    def test_participant_confirm_succeeds_with_ready_roster_after_deadline(self):
        """Test that participant confirm succeeds after the deadline once ready."""
        urgent_tournament = self.env["federation.tournament"].create(
            {
                "name": "Participant Ready Deadline Tournament",
                "code": "PRT-READY-DEADLINE",
                "season_id": self.season.id,
                "date_start": (self.today + timedelta(days=7)).isoformat(),
                "rule_set_id": self.rule_set.id,
            }
        )
        self._create_ready_roster(
            self.team,
            self.player,
            "Participant Ready Roster",
        )

        participant = self.env["federation.tournament.participant"].create(
            {
                "tournament_id": urgent_tournament.id,
                "team_id": self.team.id,
            }
        )
        participant.action_confirm()

        self.assertTrue(participant.ready_for_confirmation)
        self.assertEqual(participant.state, "confirmed")
        self.assertFalse(participant.confirmation_feedback)

    def test_match_schedule_within_deadline_requires_ready_team_rosters(self):
        """Test that match schedule within deadline requires ready team rosters."""
        urgent_tournament = self.env["federation.tournament"].create(
            {
                "name": "Roster Deadline Match Tournament",
                "code": "PRT-MATCH-DEADLINE",
                "season_id": self.season.id,
                "date_start": (self.today + timedelta(days=6)).isoformat(),
                "rule_set_id": self.rule_set.id,
            }
        )

        with self.assertRaises(ValidationError):
            self.env["federation.match"].create(
                {
                    "tournament_id": urgent_tournament.id,
                    "home_team_id": self.team.id,
                    "away_team_id": self.opponent_team.id,
                    "date_scheduled": f"{(self.today + timedelta(days=6)).isoformat()} 18:00:00",
                }
            )

    def test_match_schedule_within_deadline_allows_ready_team_rosters(self):
        """Test that match schedule within deadline allows ready team rosters."""
        urgent_tournament = self.env["federation.tournament"].create(
            {
                "name": "Roster Deadline Match Ready Tournament",
                "code": "PRT-MATCH-READY",
                "season_id": self.season.id,
                "date_start": (self.today + timedelta(days=6)).isoformat(),
                "rule_set_id": self.rule_set.id,
            }
        )
        self._create_ready_roster(self.team, self.player, "Home Deadline Roster")
        self._create_ready_roster(
            self.opponent_team,
            self.opponent_player,
            "Away Deadline Roster",
        )

        match = self.env["federation.match"].create(
            {
                "tournament_id": urgent_tournament.id,
                "home_team_id": self.team.id,
                "away_team_id": self.opponent_team.id,
                "date_scheduled": f"{(self.today + timedelta(days=6)).isoformat()} 18:00:00",
            }
        )

        self.assertTrue(match.id)
