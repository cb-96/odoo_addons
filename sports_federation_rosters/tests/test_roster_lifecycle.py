"""Focused lifecycle tests for rosters and match sheets.

Each test uses the smallest fixture possible to exercise one behaviour,
keeping setup cost and assertion scope narrow.
"""

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestRosterLifecycle(TransactionCase):
    """State transitions, lock guards, and constraint checks for team rosters."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create({"name": "Lifecycle Club"})
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Lifecycle FC",
                "club_id": cls.club.id,
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Lifecycle Season",
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
            }
        )
        cls.player1 = cls.env["federation.player"].create(
            {
                "name": "Lifecycle Player One",
                "first_name": "Lifecycle",
                "last_name": "One",
                "gender": "male",
            }
        )
        cls.player2 = cls.env["federation.player"].create(
            {
                "name": "Lifecycle Player Two",
                "first_name": "Lifecycle",
                "last_name": "Two",
                "gender": "male",
            }
        )

    def _make_roster(self, **kwargs):
        vals = {"team_id": self.team.id, "season_id": self.season.id}
        vals.update(kwargs)
        return self.env["federation.team.roster"].create(vals)

    def _add_active_line(self, roster, player):
        return self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": player.id,
                "status": "active",
            }
        )

    # ── activation ──────────────────────────────────────────────────────────

    def test_activate_with_active_line_succeeds(self):
        roster = self._make_roster()
        self._add_active_line(roster, self.player1)
        roster.action_activate()
        self.assertEqual(roster.status, "active")

    def test_activate_without_any_line_raises(self):
        roster = self._make_roster()
        with self.assertRaises(ValidationError):
            roster.action_activate()

    def test_close_sets_status_closed(self):
        roster = self._make_roster()
        self._add_active_line(roster, self.player1)
        roster.action_activate()
        roster.action_close()
        self.assertEqual(roster.status, "closed")

    def test_reopen_restores_closed_roster_to_active(self):
        roster = self._make_roster()
        self._add_active_line(roster, self.player1)
        roster.action_activate()
        roster.action_close()

        roster.action_reopen()
        self.assertEqual(roster.status, "active")

    def test_reopen_requires_closed_status(self):
        roster = self._make_roster()
        self._add_active_line(roster, self.player1)
        with self.assertRaises(ValidationError):
            roster.action_reopen()

    def test_reopen_to_draft_from_active(self):
        roster = self._make_roster()
        self._add_active_line(roster, self.player1)
        roster.action_activate()
        roster.action_set_draft()
        self.assertEqual(roster.status, "draft")

    # ── captain constraint ───────────────────────────────────────────────────

    def test_two_captains_raises(self):
        roster = self._make_roster()
        self._add_active_line(roster, self.player1)
        self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": self.player1.id,
                "status": "active",
                "is_captain": True,
                "date_from": "2025-01-01",
            }
        )
        with self.assertRaises(Exception):
            self.env["federation.team.roster.line"].create(
                {
                    "roster_id": roster.id,
                    "player_id": self.player2.id,
                    "status": "active",
                    "is_captain": True,
                    "date_from": "2025-01-02",
                }
            )

    def test_two_vice_captains_raises(self):
        roster = self._make_roster()
        self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": self.player1.id,
                "status": "active",
                "is_vice_captain": True,
            }
        )
        with self.assertRaises(Exception):
            self.env["federation.team.roster.line"].create(
                {
                    "roster_id": roster.id,
                    "player_id": self.player2.id,
                    "status": "active",
                    "is_vice_captain": True,
                }
            )

    # ── match-day lock guard ─────────────────────────────────────────────────

    def test_roster_line_locked_when_sheet_submitted(self):
        """A roster line used on a submitted match sheet cannot be modified."""
        tournament = self.env["federation.tournament"].create(
            {
                "name": "Lock Guard Tournament",
                "season_id": self.season.id,
                "date_start": "2025-06-01",
            }
        )
        team_away = self.env["federation.team"].create(
            {"name": "Away FC", "club_id": self.club.id}
        )
        match = (
            self.env["federation.match"]
            .with_context(skip_auto_match_sheets=True)
            .create(
                {
                    "tournament_id": tournament.id,
                    "home_team_id": self.team.id,
                    "away_team_id": team_away.id,
                }
            )
        )

        roster = self._make_roster()
        line = self._add_active_line(roster, self.player1)
        roster.action_activate()

        sheet = self.env["federation.match.sheet"].create(
            {
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
        self.assertEqual(sheet.state, "submitted")

        with self.assertRaises(ValidationError):
            line.write({"jersey_number": "99"})


class TestMatchSheetLifecycle(TransactionCase):
    """State transitions and edit guards for match sheets."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create({"name": "Sheet Club"})
        cls.team_home = cls.env["federation.team"].create(
            {
                "name": "Sheet Home FC",
                "club_id": cls.club.id,
            }
        )
        cls.team_away = cls.env["federation.team"].create(
            {
                "name": "Sheet Away FC",
                "club_id": cls.club.id,
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Sheet Season",
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Sheet Tournament",
                "season_id": cls.season.id,
                "date_start": "2025-01-01",
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
                }
            )
        )
        cls.player = cls.env["federation.player"].create(
            {
                "name": "Sheet Player",
                "first_name": "Sheet",
                "last_name": "Player",
                "gender": "male",
            }
        )

    def _make_sheet(self, **kwargs):
        vals = {
            "match_id": self.match.id,
            "team_id": self.team_home.id,
            "side": "home",
        }
        vals.update(kwargs)
        return self.env["federation.match.sheet"].create(vals)

    # ── state cycle ──────────────────────────────────────────────────────────

    def test_full_state_cycle(self):
        sheet = self._make_sheet()
        self.assertEqual(sheet.state, "draft")

        sheet.write({"state": "submitted"})
        self.assertEqual(sheet.state, "submitted")

        sheet.action_approve()
        self.assertEqual(sheet.state, "approved")

        sheet.action_lock()
        self.assertEqual(sheet.state, "locked")

    def test_reset_to_draft_from_submitted(self):
        sheet = self._make_sheet()
        sheet.write({"state": "submitted"})
        sheet.action_reset_to_draft()
        self.assertEqual(sheet.state, "draft")

    # ── locked-sheet guard ───────────────────────────────────────────────────

    def test_locked_sheet_blocks_write(self):
        sheet = self._make_sheet()
        sheet.write({"state": "locked"})

        with self.assertRaises(ValidationError):
            sheet.write({"notes": "shouldn't be allowed"})

    def test_locked_sheet_line_blocks_write(self):
        roster = self.env["federation.team.roster"].create(
            {
                "team_id": self.team_home.id,
                "season_id": self.season.id,
            }
        )
        line = self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": self.player.id,
                "status": "active",
            }
        )
        roster.action_activate()
        sheet = self._make_sheet(roster_id=roster.id)
        sheet_line = self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": sheet.id,
                "player_id": self.player.id,
                "roster_line_id": line.id,
                "is_starter": True,
            }
        )
        sheet.write({"state": "locked"})

        with self.assertRaises(ValidationError):
            sheet_line.write({"is_captain": True})

    # ── approved sheet guards ────────────────────────────────────────────────

    def test_approved_sheet_blocks_player_selection_change(self):
        sheet = self._make_sheet()
        sheet_line = self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": sheet.id,
                "player_id": self.player.id,
                "is_starter": True,
            }
        )
        sheet.write({"state": "approved"})

        with self.assertRaises(ValidationError):
            sheet_line.write({"is_starter": False})

    def test_approved_sheet_allows_substitution_minutes(self):
        sheet = self._make_sheet()
        sheet_line = self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": sheet.id,
                "player_id": self.player.id,
                "is_substitute": True,
            }
        )
        sheet.write({"state": "approved"})

        # substitution time recording is allowed on approved sheets
        sheet_line.write({"entered_minute": 60})
        self.assertEqual(sheet_line.entered_minute, 60)

    # ── add-player guard on approved/locked ──────────────────────────────────

    def test_cannot_add_line_to_approved_sheet(self):
        sheet = self._make_sheet()
        sheet.write({"state": "approved"})

        player2 = self.env["federation.player"].create(
            {
                "name": "Sheet Player Two",
                "first_name": "Sheet",
                "last_name": "Two",
                "gender": "male",
            }
        )
        with self.assertRaises(ValidationError):
            self.env["federation.match.sheet.line"].create(
                {
                    "match_sheet_id": sheet.id,
                    "player_id": player2.id,
                    "is_starter": True,
                }
            )
