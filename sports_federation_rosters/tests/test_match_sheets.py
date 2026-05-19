from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestMatchSheets(TransactionCase):

    def _create_active_roster(self, name, min_players=1):
        """Exercise create active roster."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": f"{name} Rules",
                "code": name.upper().replace(" ", "_")[:20],
                "squad_min_size": min_players,
            }
        )
        roster = self.env["federation.team.roster"].create(
            {
                "name": name,
                "team_id": self.team_home.id,
                "season_id": self.season.id,
                "rule_set_id": rule_set.id,
            }
        )
        line1 = self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": self.player1.id,
            }
        )
        line2 = False
        if min_players > 1:
            line2 = self.env["federation.team.roster.line"].create(
                {
                    "roster_id": roster.id,
                    "player_id": self.player2.id,
                }
            )
        roster.action_activate()
        return roster, line1, line2

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
        cls.team_home = cls.env["federation.team"].create(
            {
                "name": "Home Team",
                "club_id": cls.club.id,
                "code": "HT",
            }
        )
        cls.team_away = cls.env["federation.team"].create(
            {
                "name": "Away Team",
                "club_id": cls.club.id,
                "code": "AT",
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
                "date_start": "2024-01-01",
            }
        )
        cls.match = (
            cls.env["federation.match"]
            .with_context(skip_auto_match_sheets=True)
            .create(
                {
                    "tournament_id": cls.tournament.id,
                    "home_team_id": cls.team_home.id,
                    "away_team_id": cls.team_away.id,
                    "date_scheduled": "2024-06-15 15:00:00",
                }
            )
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

    def test_create_match_sheet(self):
        """Test basic match sheet creation."""
        sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Home Sheet",
                "match_id": self.match.id,
                "team_id": self.team_home.id,
                "side": "home",
            }
        )
        self.assertTrue(sheet.id)
        self.assertEqual(sheet.state, "draft")
        self.assertEqual(sheet.match_id, self.match)
        self.assertEqual(sheet.team_id, self.team_home)

    def test_match_sheet_unique_per_match_team_side(self):
        """Test that only one match sheet per match/team/side combination exists."""
        # Create first sheet
        self.env["federation.match.sheet"].create(
            {
                "name": "Home Sheet",
                "match_id": self.match.id,
                "team_id": self.team_home.id,
                "side": "home",
            }
        )

        # Try to create duplicate - should fail
        with self.assertRaises(Exception):
            self.env["federation.match.sheet"].create(
                {
                    "name": "Duplicate Home Sheet",
                    "match_id": self.match.id,
                    "team_id": self.team_home.id,
                    "side": "home",
                }
            )

    def test_match_sheet_side_team_consistency(self):
        """Test that home/away side must match match teams."""
        # Test home side with wrong team
        with self.assertRaises(ValidationError):
            self.env["federation.match.sheet"].create(
                {
                    "name": "Wrong Home Sheet",
                    "match_id": self.match.id,
                    "team_id": self.team_away.id,
                    "side": "home",
                }
            )

        # Test away side with wrong team
        with self.assertRaises(ValidationError):
            self.env["federation.match.sheet"].create(
                {
                    "name": "Wrong Away Sheet",
                    "match_id": self.match.id,
                    "team_id": self.team_home.id,
                    "side": "away",
                }
            )

        # Test correct home side
        home_sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Correct Home Sheet",
                "match_id": self.match.id,
                "team_id": self.team_home.id,
                "side": "home",
            }
        )
        self.assertEqual(home_sheet.team_id, self.match.home_team_id)

        # Test correct away side
        away_sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Correct Away Sheet",
                "match_id": self.match.id,
                "team_id": self.team_away.id,
                "side": "away",
            }
        )
        self.assertEqual(away_sheet.team_id, self.match.away_team_id)

    def test_match_sheet_line_unique_player(self):
        """Test that a player cannot appear twice on same match sheet."""
        sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Test Sheet",
                "match_id": self.match.id,
                "team_id": self.team_home.id,
                "side": "home",
            }
        )

        # Create first line
        self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": sheet.id,
                "player_id": self.player1.id,
            }
        )

        # Try to create duplicate - should fail
        with self.assertRaises(Exception):
            self.env["federation.match.sheet.line"].create(
                {
                    "match_sheet_id": sheet.id,
                    "player_id": self.player1.id,
                }
            )

    def test_match_sheet_line_starter_substitute_validation(self):
        """Test that a player cannot be both starter and substitute."""
        sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Test Sheet",
                "match_id": self.match.id,
                "team_id": self.team_home.id,
                "side": "home",
            }
        )

        # Test invalid combination
        with self.assertRaises(ValidationError):
            self.env["federation.match.sheet.line"].create(
                {
                    "match_sheet_id": sheet.id,
                    "player_id": self.player1.id,
                    "is_starter": True,
                    "is_substitute": True,
                }
            )

    def test_match_sheet_submit_blocks_ineligible_players_with_reason(self):
        """Test that match sheet submit blocks ineligible players with reason."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Match Suspension Rules",
                "code": "MSR",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "No Suspended Players",
                "eligibility_type": "suspension",
            }
        )
        self.tournament.write({"rule_set_id": rule_set.id})

        roster = self.env["federation.team.roster"].create(
            {
                "name": "Home Active Roster",
                "team_id": self.team_home.id,
                "season_id": self.season.id,
                "rule_set_id": rule_set.id,
            }
        )
        roster_line = self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": self.player1.id,
            }
        )
        roster.action_activate()
        self.player1.write({"state": "suspended"})

        sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Eligibility Sheet",
                "match_id": self.match.id,
                "team_id": self.team_home.id,
                "roster_id": roster.id,
                "side": "home",
            }
        )
        line = self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": sheet.id,
                "player_id": self.player1.id,
                "roster_line_id": roster_line.id,
            }
        )

        line.invalidate_recordset()
        self.assertFalse(line.eligible)
        self.assertIn("suspended", line.eligibility_feedback.lower())
        with self.assertRaises(ValidationError):
            sheet.action_submit()

    def test_match_sheet_submit_enforces_squad_minimum(self):
        """Test that match sheet submit enforces squad minimum."""
        roster, roster_line, _second_line = self._create_active_roster(
            "Sized Roster",
            min_players=2,
        )

        sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Sized Sheet",
                "match_id": self.match.id,
                "team_id": self.team_home.id,
                "roster_id": roster.id,
                "side": "home",
            }
        )
        self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": sheet.id,
                "player_id": self.player1.id,
                "roster_line_id": roster_line.id,
            }
        )

        self.assertFalse(sheet.ready_for_submission)
        self.assertIn("required minimum of 2", sheet.readiness_feedback)
        with self.assertRaises(ValidationError):
            sheet.action_submit()

    def test_match_sheet_reset_to_draft_requires_submitted_state(self):
        """Test reset to draft only works from submitted match sheets."""
        roster, roster_line, _unused = self._create_active_roster(
            "Reset Sheet Roster",
            min_players=1,
        )
        sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Reset Sheet",
                "match_id": self.match.id,
                "team_id": self.team_home.id,
                "roster_id": roster.id,
                "side": "home",
            }
        )
        self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": sheet.id,
                "player_id": self.player1.id,
                "roster_line_id": roster_line.id,
                "is_starter": True,
            }
        )

        with self.assertRaises(ValidationError):
            sheet.action_reset_to_draft()
        self.assertEqual(sheet.state, "draft")

        sheet.action_submit()
        self.assertEqual(sheet.state, "submitted")

        sheet.action_reset_to_draft()
        self.assertEqual(sheet.state, "draft")
        self.assertIn(
            "match_sheet_reset",
            sheet.audit_event_ids.mapped("event_type"),
        )

    def test_match_sheet_substitution_minutes_require_valid_roles(self):
        """Test that match sheet substitution minutes require valid roles."""
        sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Substitution Rules Sheet",
                "match_id": self.match.id,
                "team_id": self.team_home.id,
                "side": "home",
            }
        )

        with self.assertRaises(ValidationError):
            self.env["federation.match.sheet.line"].create(
                {
                    "match_sheet_id": sheet.id,
                    "player_id": self.player1.id,
                    "entered_minute": 15,
                }
            )

    def test_approved_match_sheet_allows_substitution_updates_but_not_lineup_changes(
        self,
    ):
        """Test that approved match sheet allows substitution updates but not lineup changes."""
        roster, _starter_line, line_roster = self._create_active_roster(
            "Approved Sheet Roster",
            min_players=1,
        )
        sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Approved Sheet",
                "match_id": self.match.id,
                "team_id": self.team_home.id,
                "roster_id": roster.id,
                "side": "home",
            }
        )
        line = self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": sheet.id,
                "player_id": self.player1.id,
                "roster_line_id": _starter_line.id,
                "is_substitute": True,
            }
        )
        sheet.action_submit()
        sheet.action_approve()

        line.write({"entered_minute": 42})
        self.assertEqual(line.entered_minute, 42)
        self.assertEqual(sheet.substitution_count, 1)
        self.assertIn(
            "substitution_recorded",
            sheet.audit_event_ids.mapped("event_type"),
        )

        with self.assertRaises(ValidationError):
            line.write({"jersey_number": "12"})

    def test_lock_blocks_any_further_match_sheet_changes(self):
        """Test that lock blocks any further match sheet changes."""
        roster, starter_line, _unused = self._create_active_roster(
            "Locked Sheet Roster",
            min_players=1,
        )
        sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Locked Sheet",
                "match_id": self.match.id,
                "team_id": self.team_home.id,
                "roster_id": roster.id,
                "side": "home",
            }
        )
        line = self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": sheet.id,
                "player_id": self.player1.id,
                "roster_line_id": starter_line.id,
                "is_starter": True,
            }
        )
        sheet.action_submit()
        sheet.action_approve()
        sheet.action_lock()

        with self.assertRaises(ValidationError):
            sheet.write({"notes": "Locked"})
        with self.assertRaises(ValidationError):
            line.write({"notes": "Not allowed"})

    def test_auto_match_sheets_created_on_match_create(self):
        """Creating a match auto-creates draft sheets for home and away teams."""
        # Create an active roster so it can be linked
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Auto Sheet Rules",
                "code": "AUTO_RS",
            }
        )
        roster = self.env["federation.team.roster"].create(
            {
                "name": "Auto Roster",
                "team_id": self.team_home.id,
                "season_id": self.season.id,
                "rule_set_id": rule_set.id,
            }
        )
        player = self.env["federation.player"].create(
            {
                "name": "Auto Player",
                "first_name": "Auto",
                "last_name": "Player",
                "gender": "male",
            }
        )
        self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": player.id,
            }
        )
        roster.action_activate()

        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team_home.id,
                "away_team_id": self.team_away.id,
            }
        )
        sheets = self.env["federation.match.sheet"].search(
            [("match_id", "=", match.id)]
        )
        self.assertEqual(len(sheets), 2)
        sides = set(sheets.mapped("side"))
        self.assertIn("home", sides)
        self.assertIn("away", sides)
        for sheet in sheets:
            self.assertEqual(sheet.state, "draft")

        home_sheet = sheets.filtered(lambda s: s.side == "home")
        self.assertEqual(
            home_sheet.roster_id,
            roster,
            "Home sheet should be linked to the active roster",
        )

    def test_auto_match_sheets_no_duplicate_on_second_create(self):
        """Auto-creation is skipped when a sheet already exists for that side."""
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team_home.id,
                "away_team_id": self.team_away.id,
            }
        )
        # Calling _create_auto_match_sheets again should not raise or duplicate
        match._create_auto_match_sheets()
        sheets = self.env["federation.match.sheet"].search(
            [("match_id", "=", match.id)]
        )
        self.assertEqual(len(sheets), 2)
