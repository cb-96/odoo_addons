from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestRosters(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Test Club",
                "code": "TEST",
            }
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Test Team",
                "club_id": cls.club.id,
                "code": "TT",
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
        cls.competition = cls.env["federation.competition"].create(
            {
                "name": "Test Competition",
                "code": "TC",
            }
        )
        cls.player1 = cls.env["federation.player"].create(
            {
                "name": "Player One",
                "first_name": "Player",
                "last_name": "One",
                "gender": "male",
            }
        )
        cls.player2 = cls.env["federation.player"].create(
            {
                "name": "Player Two",
                "first_name": "Player",
                "last_name": "Two",
                "gender": "male",
            }
        )

    def test_create_roster(self):
        """Test basic roster creation."""
        roster = self.env["federation.team.roster"].create(
            {
                "name": "Test Roster",
                "team_id": self.team.id,
                "season_id": self.season.id,
                "competition_id": self.competition.id,
            }
        )
        self.assertTrue(roster.id)
        self.assertEqual(roster.status, "draft")
        self.assertEqual(roster.team_id, self.team)
        self.assertEqual(roster.season_id, self.season)

    def test_create_roster_generates_name_from_scope(self):
        """Test that create roster generates name from scope."""
        roster = self.env["federation.team.roster"].create(
            {
                "team_id": self.team.id,
                "season_id": self.season.id,
                "competition_id": self.competition.id,
            }
        )

        self.assertTrue(roster.name)
        self.assertIn(self.team.display_name, roster.name)
        self.assertIn(self.season.display_name, roster.name)
        self.assertIn(self.competition.display_name, roster.name)

    def test_team_roster_button_opens_single_roster_form(self):
        """Test that team roster button opens single roster form."""
        roster = self.env["federation.team.roster"].create(
            {
                "team_id": self.team.id,
                "season_id": self.season.id,
            }
        )

        action = self.team.action_view_rosters()

        self.assertEqual(action["view_mode"], "form")
        self.assertEqual(action["res_id"], roster.id)

    def test_roster_team_season_registration_consistency(self):
        """Test that season registration must match team and season."""
        registration = self.env["federation.season.registration"].create(
            {
                "name": "Test Registration",
                "team_id": self.team.id,
                "season_id": self.season.id,
            }
        )

        # Create roster with matching registration - should work
        roster = self.env["federation.team.roster"].create(
            {
                "name": "Test Roster",
                "team_id": self.team.id,
                "season_id": self.season.id,
                "season_registration_id": registration.id,
            }
        )
        self.assertEqual(roster.season_registration_id, registration)

        # Create another team and season to test mismatch
        other_team = self.env["federation.team"].create(
            {
                "name": "Other Team",
                "club_id": self.club.id,
                "code": "OT",
            }
        )
        other_season = self.env["federation.season"].create(
            {
                "name": "Other Season",
                "code": "OS2024",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )

        # Test team mismatch
        with self.assertRaises(ValidationError):
            self.env["federation.team.roster"].create(
                {
                    "name": "Bad Roster Team",
                    "team_id": other_team.id,
                    "season_id": self.season.id,
                    "season_registration_id": registration.id,
                }
            )

        # Test season mismatch
        with self.assertRaises(ValidationError):
            self.env["federation.team.roster"].create(
                {
                    "name": "Bad Roster Season",
                    "team_id": self.team.id,
                    "season_id": other_season.id,
                    "season_registration_id": registration.id,
                }
            )

    def test_roster_line_unique_player_constraint(self):
        """Test that a player cannot have duplicate roster lines with same date_from."""
        roster = self.env["federation.team.roster"].create(
            {
                "name": "Test Roster",
                "team_id": self.team.id,
                "season_id": self.season.id,
            }
        )

        # Create first line
        self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": self.player1.id,
                "date_from": "2024-01-01",
            }
        )

        # Try to create duplicate - should fail
        with self.assertRaises(Exception):
            self.env["federation.team.roster.line"].create(
                {
                    "roster_id": roster.id,
                    "player_id": self.player1.id,
                    "date_from": "2024-01-01",
                }
            )

    def test_single_active_captain_constraint(self):
        """Test that only one active captain is allowed per roster."""
        roster = self.env["federation.team.roster"].create(
            {
                "name": "Test Roster",
                "team_id": self.team.id,
                "season_id": self.season.id,
            }
        )

        # Create first captain
        self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": self.player1.id,
                "is_captain": True,
                "status": "active",
            }
        )

        # Try to create second captain - should fail
        with self.assertRaises(ValidationError):
            self.env["federation.team.roster.line"].create(
                {
                    "roster_id": roster.id,
                    "player_id": self.player2.id,
                    "is_captain": True,
                    "status": "active",
                }
            )

    def test_roster_line_date_validation(self):
        """Test that date_to cannot be before date_from."""
        roster = self.env["federation.team.roster"].create(
            {
                "name": "Test Roster",
                "team_id": self.team.id,
                "season_id": self.season.id,
            }
        )

        # Test invalid dates
        with self.assertRaises(ValidationError):
            self.env["federation.team.roster.line"].create(
                {
                    "roster_id": roster.id,
                    "player_id": self.player1.id,
                    "date_from": "2024-12-31",
                    "date_to": "2024-01-01",
                }
            )

    def test_roster_line_rejects_gender_mismatch(self):
        """Players cannot be added to a single-gender team with the wrong gender."""
        female_team = self.env["federation.team"].create(
            {
                "name": "Female Team",
                "club_id": self.club.id,
                "code": "FT",
                "gender": "female",
            }
        )
        male_player = self.env["federation.player"].create(
            {
                "first_name": "Male",
                "last_name": "Player",
                "gender": "male",
            }
        )
        roster = self.env["federation.team.roster"].create(
            {
                "name": "Female Team Roster",
                "team_id": female_team.id,
                "season_id": self.season.id,
            }
        )

        with self.assertRaises(ValidationError):
            self.env["federation.team.roster.line"].create(
                {
                    "roster_id": roster.id,
                    "player_id": male_player.id,
                }
            )

    def test_roster_activation_blocks_lines_with_invalid_season_license(self):
        """Test that roster activation blocks lines with invalid season license."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Roster License Rules",
                "code": "RLR",
                "squad_min_size": 1,
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Season License Required",
                "eligibility_type": "license_valid",
            }
        )
        roster = self.env["federation.team.roster"].create(
            {
                "name": "Licensed Roster",
                "team_id": self.team.id,
                "season_id": self.season.id,
                "rule_set_id": rule_set.id,
            }
        )
        license_record = self.env["federation.player.license"].create(
            {
                "name": "LIC-ROSTER-1",
                "player_id": self.player1.id,
                "season_id": self.season.id,
                "club_id": self.club.id,
                "issue_date": "2024-01-01",
                "expiry_date": "2099-12-31",
                "state": "active",
            }
        )
        line = self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": self.player1.id,
                "license_id": license_record.id,
            }
        )

        roster.action_activate()
        self.assertEqual(roster.status, "active")

        license_record.write({"state": "cancelled"})
        line.invalidate_recordset()
        roster.invalidate_recordset()
        self.assertFalse(line.eligible)
        self.assertIn("not active", line.eligibility_feedback.lower())
        self.assertFalse(roster.ready_for_activation)
        self.assertIn(self.player1.display_name, roster.readiness_feedback)

    def test_live_match_sheet_locks_roster_scope_and_used_lines(self):
        """Test that live match sheet locks roster scope and used lines."""
        roster = self.env["federation.team.roster"].create(
            {
                "name": "Locked Scope Roster",
                "team_id": self.team.id,
                "season_id": self.season.id,
            }
        )
        line = self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": self.player1.id,
            }
        )
        roster.action_activate()
        match = (
            self.env["federation.match"]
            .with_context(skip_auto_match_sheets=True)
            .create(
                {
                    "tournament_id": self.env["federation.tournament"]
                    .create(
                        {
                            "name": "Roster Lock Tournament",
                            "code": "RLT",
                            "season_id": self.season.id,
                            "date_start": "2024-02-01",
                        }
                    )
                    .id,
                    "home_team_id": self.team.id,
                    "away_team_id": self.env["federation.team"]
                    .create(
                        {
                            "name": "Opponent Team",
                            "club_id": self.club.id,
                            "code": "OTL",
                        }
                    )
                    .id,
                    "date_scheduled": "2024-02-10 15:00:00",
                }
            )
        )
        sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Locked Scope Sheet",
                "match_id": match.id,
                "team_id": self.team.id,
                "roster_id": roster.id,
                "side": "home",
            }
        )
        self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": sheet.id,
                "player_id": self.player1.id,
                "roster_line_id": line.id,
                "is_starter": True,
            }
        )
        sheet.action_submit()

        self.assertTrue(roster.match_day_locked)
        with self.assertRaises(ValidationError):
            roster.write({"valid_to": "2024-12-15"})
        with self.assertRaises(ValidationError):
            line.write({"status": "inactive"})

    def test_roster_audit_events_are_created_for_lifecycle_changes(self):
        """Test that roster audit events are created for lifecycle changes."""
        roster = self.env["federation.team.roster"].create(
            {
                "name": "Audited Roster",
                "team_id": self.team.id,
                "season_id": self.season.id,
            }
        )
        self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": self.player1.id,
            }
        )
        roster.action_activate()

        event_types = roster.audit_event_ids.mapped("event_type")
        self.assertIn("roster_created", event_types)
        self.assertIn("roster_line_added", event_types)
        self.assertIn("roster_activated", event_types)
