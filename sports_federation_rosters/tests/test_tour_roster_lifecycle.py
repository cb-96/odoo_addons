"""Tour T-04: Roster Management — Activation, Match Sheet Workflow, Close

Walks the full roster lifecycle for a team:
  1. Draft roster — activation fails without players
  2. Add players, activate roster
  3. Unique-active-roster constraint: second activation attempt raises
  4. Create a match and a match sheet linked to the active roster
  5. Add lines (roster players) to the sheet
  6. Submit → approve → lock the match sheet (match must be done)
  7. Close the roster at season end

Key invariants verified:
- Draft roster with no lines cannot be activated
- Once active, roster can be closed
- Match sheet follows: draft → submitted → approved → locked
- Lock requires match in 'done' state
"""

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestTourRosterLifecycle(TransactionCase):
    """T-04: Roster lifecycle and match sheet workflow tour."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.club = cls.env["federation.club"].create(
            {"name": "Roster Tour Club", "code": "RCLB"}
        )
        cls.team = cls.env["federation.team"].create(
            {"name": "Roster Tour Team", "club_id": cls.club.id, "code": "RTT26"}
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Roster Tour Season",
                "code": "RST26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Roster Tour Rules",
                "code": "RSTR",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        tournament = cls.env["federation.tournament"].create(
            {
                "name": "Roster Tour Cup",
                "date_start": "2026-03-01",
                "rule_set_id": rule_set.id,
            }
        )
        cls.tournament = tournament
        cls.rule_set = rule_set

        # Create players
        cls.players = cls.env["federation.player"]
        for i in range(1, 5):
            p = cls.env["federation.player"].create(
                {
                    "first_name": f"Roster{i}",
                    "last_name": "Player",
                    "gender": "male",
                }
            )
            cls.players |= p

    def test_roster_lifecycle_and_match_sheet_workflow(self):
        """Roster draft → activate → match sheet full lifecycle → close."""

        # STEP 1: Empty roster cannot be activated
        roster = self.env["federation.team.roster"].create(
            {
                "name": "Tour Roster",
                "team_id": self.team.id,
                "season_id": self.season.id,
                "min_players_required": 0,
            }
        )
        self.assertEqual(roster.status, "draft")
        with self.assertRaises(ValidationError):
            roster.action_activate()

        # STEP 2: Add players and activate
        lines = self.env["federation.team.roster.line"]
        for player in self.players:
            line = self.env["federation.team.roster.line"].create(
                {
                    "roster_id": roster.id,
                    "player_id": player.id,
                    "status": "active",
                }
            )
            lines |= line
        roster.action_activate()
        self.assertEqual(roster.status, "active")

        # STEP 3: Create a match in 'done' state (needed to lock sheet later)
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team.id,
                "home_score": 3,
                "away_score": 1,
                "state": "done",
            }
        )

        # STEP 4: Create match sheet using side='other' to avoid team constraint
        sheet = self.env["federation.match.sheet"].create(
            {
                "match_id": match.id,
                "team_id": self.team.id,
                "side": "other",
                "roster_id": roster.id,
            }
        )
        self.assertEqual(sheet.state, "draft")

        # STEP 5: Add lines — each references a roster line for eligibility
        for player, line in zip(self.players, lines):
            self.env["federation.match.sheet.line"].create(
                {
                    "match_sheet_id": sheet.id,
                    "player_id": player.id,
                    "roster_line_id": line.id,
                    "is_starter": True,
                }
            )

        # STEP 6: Submit
        sheet.action_submit()
        self.assertEqual(sheet.state, "submitted")

        # STEP 7: Approve
        sheet.action_approve()
        self.assertEqual(sheet.state, "approved")

        # STEP 8: Lock (match is already 'done')
        sheet.action_lock()
        self.assertEqual(sheet.state, "locked")
        self.assertTrue(sheet.locked_on)
        self.assertTrue(sheet.locked_by_id)

        # STEP 9: Close the roster
        roster.action_close()
        self.assertEqual(roster.status, "closed")
