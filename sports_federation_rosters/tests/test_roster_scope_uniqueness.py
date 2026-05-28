"""Regression tests for roster scope uniqueness (Phase 2, Items 3 & 4).

Verifies the correct semantics after removing the name-based unique constraint:

  - Multiple draft/closed rosters for the same (team, season, competition) are
    ALLOWED.  The "close old → create new" workflow must continue to work.
  - Only one ACTIVE roster per scope is allowed (enforced by DB partial unique
    indexes added in 19.0.1.4.0 and the Python _assert_unique_active_roster check).
  - Auto-generated names use the base pattern without a search-count suffix loop
    (removing the race condition: the loop was only needed to avoid the name-based
    constraint, which is now gone).
"""

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestRosterScopeUniqueness(TransactionCase):
    """Scope and name semantics after removing the name-based unique constraint."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {"name": "Scope Club", "code": "SCL"}
        )
        cls.team = cls.env["federation.team"].create(
            {"name": "Scope Team", "club_id": cls.club.id, "code": "SCT"}
        )
        cls.team_b = cls.env["federation.team"].create(
            {"name": "Scope Team B", "club_id": cls.club.id, "code": "SCTB"}
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Scope Season",
                "code": "SCSS",
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
            }
        )
        cls.season_b = cls.env["federation.season"].create(
            {
                "name": "Scope Season B",
                "code": "SCSSB",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.competition = cls.env["federation.competition"].create(
            {"name": "Scope Competition", "code": "SCCO"}
        )
        cls.player = cls.env["federation.player"].create(
            {
                "first_name": "Scope",
                "last_name": "Player",
                "gender": "male",
                "club_id": cls.club.id,
            }
        )

    # ------------------------------------------------------------------
    # Multiple draft/closed rosters per scope are allowed
    # ------------------------------------------------------------------

    def test_two_draft_rosters_same_scope_allowed(self):
        """Two draft rosters for the same scope do NOT raise an error."""
        r1 = self.env["federation.team.roster"].create(
            {"team_id": self.team.id, "season_id": self.season.id}
        )
        r2 = self.env["federation.team.roster"].create(
            {"team_id": self.team.id, "season_id": self.season.id}
        )
        self.assertTrue(r1 and r2, "Both draft rosters must exist")
        self.assertEqual(r1.status, "draft")
        self.assertEqual(r2.status, "draft")

    def test_close_active_then_create_new_draft_allowed(self):
        """Closing the active roster and creating a new draft for same scope is allowed."""
        r1 = self.env["federation.team.roster"].create(
            {
                "team_id": self.team.id,
                "season_id": self.season.id,
                "competition_id": self.competition.id,
            }
        )
        self.env["federation.team.roster.line"].create(
            {"roster_id": r1.id, "player_id": self.player.id}
        )
        r1.action_activate()
        self.assertEqual(r1.status, "active")
        r1.action_close()
        self.assertEqual(r1.status, "closed")

        r2 = self.env["federation.team.roster"].create(
            {
                "team_id": self.team.id,
                "season_id": self.season.id,
                "competition_id": self.competition.id,
            }
        )
        self.assertEqual(r2.status, "draft")

    # ------------------------------------------------------------------
    # Active-roster uniqueness is still enforced
    # ------------------------------------------------------------------

    def test_two_active_rosters_same_scope_blocked(self):
        """Activating a second roster for the same scope raises ValidationError."""
        r1 = self.env["federation.team.roster"].create(
            {"team_id": self.team.id, "season_id": self.season.id}
        )
        self.env["federation.team.roster.line"].create(
            {"roster_id": r1.id, "player_id": self.player.id}
        )
        r1.action_activate()

        r2 = self.env["federation.team.roster"].create(
            {"team_id": self.team.id, "season_id": self.season.id}
        )
        self.env["federation.team.roster.line"].create(
            {"roster_id": r2.id, "player_id": self.player.id}
        )
        with self.assertRaises(ValidationError):
            r2.action_activate()

    # ------------------------------------------------------------------
    # Different scopes are independent
    # ------------------------------------------------------------------

    def test_different_teams_same_season_allowed(self):
        """Two rosters for different teams in the same season are allowed."""
        r1 = self.env["federation.team.roster"].create(
            {"team_id": self.team.id, "season_id": self.season.id}
        )
        r2 = self.env["federation.team.roster"].create(
            {"team_id": self.team_b.id, "season_id": self.season.id}
        )
        self.assertTrue(r1 and r2)

    def test_season_scope_and_competition_scope_are_distinct(self):
        """A season-only roster and a competition roster for the same team/season are independent."""
        r_season = self.env["federation.team.roster"].create(
            {"team_id": self.team.id, "season_id": self.season.id}
        )
        r_comp = self.env["federation.team.roster"].create(
            {
                "team_id": self.team.id,
                "season_id": self.season.id,
                "competition_id": self.competition.id,
            }
        )
        self.assertTrue(r_season and r_comp)

    # ------------------------------------------------------------------
    # Name generation: no collision-avoidance suffix loop
    # ------------------------------------------------------------------

    def test_auto_generated_name_uses_base_pattern(self):
        """Auto-generated name is the base pattern with no search-count suffix."""
        roster = self.env["federation.team.roster"].create(
            {"team_id": self.team.id, "season_id": self.season.id}
        )
        self.assertIn(self.team.display_name, roster.name)
        self.assertIn(self.season.display_name, roster.name)
        # Name must NOT end with a collision-avoidance suffix like " (2)"
        self.assertNotIn(" (2)", roster.name)

    def test_two_rosters_same_scope_may_share_auto_name(self):
        """Two draft rosters in the same scope get the same auto-generated name (name is not a key)."""
        r1 = self.env["federation.team.roster"].create(
            {"team_id": self.team.id, "season_id": self.season.id}
        )
        r2 = self.env["federation.team.roster"].create(
            {"team_id": self.team.id, "season_id": self.season.id}
        )
        # Both rosters have the same base name — no longer need to differ
        self.assertEqual(r1.name, r2.name)
