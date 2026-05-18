"""Tests for the result portal approval and contest flow.

These tests verify the business logic the portal controller relies on:
- Domain scoping keeps each club's results private
- action_approve_result() succeeds via sudo() for verified results
- action_contest_result() requires a non-empty reason
- Wrong-state transitions raise ValidationError
"""
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

_VISIBLE_RESULT_STATES = ("submitted", "verified", "approved", "contested")


class TestResultPortalAccess(TransactionCase):
    """Portal result approval and contest flow access tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.portal_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.role_type = cls.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )

        # Two clubs each with one team
        cls.club_a = cls.env["federation.club"].create(
            {"name": "Result Portal Club A", "code": "RPA"}
        )
        cls.club_b = cls.env["federation.club"].create(
            {"name": "Result Portal Club B", "code": "RPB"}
        )
        cls.team_a = cls.env["federation.team"].create(
            {"name": "Result Portal Team A", "club_id": cls.club_a.id, "code": "RPTA"}
        )
        cls.team_b = cls.env["federation.team"].create(
            {"name": "Result Portal Team B", "club_id": cls.club_b.id, "code": "RPTB"}
        )

        # Portal users representing each club
        def _make_portal_user(name, login, club):
            user = (
                cls.env["res.users"]
                .with_context(no_reset_password=True)
                .create(
                    {
                        "name": name,
                        "login": login,
                        "email": login,
                        "group_ids": [(6, 0, [cls.portal_group.id])],
                    }
                )
            )
            cls.env["federation.club.representative"].create(
                {
                    "club_id": club.id,
                    "partner_id": user.partner_id.id,
                    "user_id": user.id,
                    "role_type_id": cls.role_type.id,
                }
            )
            return user

        cls.user_a = _make_portal_user("Result Rep A", "result.rep.a@example.com", cls.club_a)
        cls.user_b = _make_portal_user("Result Rep B", "result.rep.b@example.com", cls.club_b)

        # Tournament with matches
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Result Portal Season",
                "code": "RPS",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Result Portal Tournament",
                "code": "RPT",
                "season_id": cls.season.id,
                "date_start": "2026-06-01",
            }
        )
        # Match between club_a (home) and club_b (away)
        cls.match_ab = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team_a.id,
                "away_team_id": cls.team_b.id,
                "date_scheduled": "2026-06-15 18:00:00",
                "home_score": 2,
                "away_score": 1,
            }
        )
        # Match only involving club_a teams (two club_a teams would need another team;
        # use two matches from club_a's POV — one as home, one as away with team_b)
        cls.match_ba = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team_b.id,
                "away_team_id": cls.team_a.id,
                "date_scheduled": "2026-06-22 18:00:00",
                "home_score": 0,
                "away_score": 3,
            }
        )

    # ------------------------------------------------------------------
    # Domain / visibility tests
    # ------------------------------------------------------------------

    def _result_domain(self, user):
        """Compute the visibility domain as the controller does."""
        clubs = user.portal_club_scope_ids
        if not clubs:
            return [("id", "=", False)]
        return [
            ("result_state", "in", list(_VISIBLE_RESULT_STATES)),
            "|",
            ("home_team_id.club_id", "in", clubs.ids),
            ("away_team_id.club_id", "in", clubs.ids),
        ]

    def test_no_results_when_state_is_draft(self):
        """Draft results are not visible via the portal domain."""
        self.match_ab.write({"result_state": "draft"})
        self.match_ba.write({"result_state": "draft"})

        domain = self._result_domain(self.user_a)
        matches = self.env["federation.match"].sudo().search(domain)
        self.assertNotIn(self.match_ab, matches)
        self.assertNotIn(self.match_ba, matches)

    def test_submitted_result_visible_to_home_club_rep(self):
        """A submitted result is visible to the home club representative."""
        self.match_ab.write({"result_state": "submitted"})

        domain = self._result_domain(self.user_a)
        matches = self.env["federation.match"].sudo().search(domain)
        self.assertIn(self.match_ab, matches)

    def test_submitted_result_visible_to_away_club_rep(self):
        """A submitted result is visible to the away club representative."""
        self.match_ab.write({"result_state": "submitted"})

        domain = self._result_domain(self.user_b)
        matches = self.env["federation.match"].sudo().search(domain)
        self.assertIn(self.match_ab, matches)

    def test_result_not_visible_to_unrelated_club_rep(self):
        """A result is not visible to a portal user from an unrelated club."""
        # Create a third unrelated club / user
        club_c = self.env["federation.club"].create(
            {"name": "Unrelated Club C", "code": "UCC"}
        )
        user_c = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Unrelated Rep C",
                    "login": "unrelated.rep.c@example.com",
                    "email": "unrelated.rep.c@example.com",
                    "group_ids": [(6, 0, [self.portal_group.id])],
                }
            )
        )
        self.env["federation.club.representative"].create(
            {
                "club_id": club_c.id,
                "partner_id": user_c.partner_id.id,
                "user_id": user_c.id,
                "role_type_id": self.role_type.id,
            }
        )
        self.match_ab.write({"result_state": "submitted"})

        domain = self._result_domain(user_c)
        matches = self.env["federation.match"].sudo().search(domain)
        self.assertNotIn(self.match_ab, matches)

    # ------------------------------------------------------------------
    # Access assertion helper
    # ------------------------------------------------------------------

    def _assert_result_access(self, match, user):
        """Mirror the controller's _assert_result_access helper."""
        clubs = user.portal_club_scope_ids
        return (
            match.home_team_id.club_id in clubs
            or match.away_team_id.club_id in clubs
        )

    def test_access_assertion_home_club(self):
        """Home club rep passes the access assertion."""
        self.assertTrue(self._assert_result_access(self.match_ab, self.user_a))

    def test_access_assertion_away_club(self):
        """Away club rep passes the access assertion."""
        self.assertTrue(self._assert_result_access(self.match_ab, self.user_b))

    def test_access_assertion_unrelated_club_denied(self):
        """A rep from an unrelated club fails the access assertion."""
        club_x = self.env["federation.club"].create(
            {"name": "Access Denied Club X", "code": "ADCX"}
        )
        user_x = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Access Denied Rep X",
                    "login": "access.denied.x@example.com",
                    "email": "access.denied.x@example.com",
                    "group_ids": [(6, 0, [self.portal_group.id])],
                }
            )
        )
        self.env["federation.club.representative"].create(
            {
                "club_id": club_x.id,
                "partner_id": user_x.partner_id.id,
                "user_id": user_x.id,
                "role_type_id": self.role_type.id,
            }
        )
        self.assertFalse(self._assert_result_access(self.match_ab, user_x))

    # ------------------------------------------------------------------
    # Approve action
    # ------------------------------------------------------------------

    def test_approve_requires_verified_state(self):
        """action_approve_result() raises if the result is not verified."""
        self.match_ab.write({"result_state": "submitted"})
        with self.assertRaises(ValidationError):
            self.match_ab.sudo().action_approve_result()

    def test_approve_verified_result_transitions_to_approved(self):
        """action_approve_result() succeeds for a verified result via sudo."""
        # Mark as submitted first so audit trail is valid, then move to verified
        self.match_ab.write(
            {
                "result_state": "verified",
                "result_submitted_by_id": False,
                "result_verified_by_id": False,
            }
        )
        self.match_ab.sudo().action_approve_result()
        self.assertEqual(self.match_ab.result_state, "approved")
        self.assertTrue(self.match_ab.include_in_official_standings)

    # ------------------------------------------------------------------
    # Contest action
    # ------------------------------------------------------------------

    def test_contest_requires_reason(self):
        """action_contest_result() raises if result_contest_reason is empty."""
        self.match_ab.write(
            {"result_state": "submitted", "result_contest_reason": False}
        )
        with self.assertRaises(ValidationError):
            self.match_ab.sudo().action_contest_result()

    def test_contest_submitted_result_with_reason_transitions_to_contested(self):
        """action_contest_result() transitions a submitted result to contested."""
        self.match_ab.write(
            {
                "result_state": "submitted",
                "result_contest_reason": "Score recorded incorrectly.",
            }
        )
        self.match_ab.sudo().action_contest_result()
        self.assertEqual(self.match_ab.result_state, "contested")
        self.assertFalse(self.match_ab.include_in_official_standings)

    def test_contest_verified_result_transitions_to_contested(self):
        """action_contest_result() transitions a verified result to contested."""
        self.match_ab.write(
            {
                "result_state": "verified",
                "result_contest_reason": "Wrong team listed as home.",
            }
        )
        self.match_ab.sudo().action_contest_result()
        self.assertEqual(self.match_ab.result_state, "contested")

    def test_contest_draft_result_raises(self):
        """action_contest_result() raises if result is in draft state."""
        self.match_ab.write(
            {
                "result_state": "draft",
                "result_contest_reason": "Reason provided.",
            }
        )
        with self.assertRaises(ValidationError):
            self.match_ab.sudo().action_contest_result()

    # ------------------------------------------------------------------
    # No portal scope
    # ------------------------------------------------------------------

    def test_no_scope_domain_returns_empty_domain(self):
        """A user with no club scope gets an empty-result domain."""
        # Create a user with portal group but no representative link
        isolated_user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Isolated Portal User",
                    "login": "isolated.portal@example.com",
                    "email": "isolated.portal@example.com",
                    "group_ids": [(6, 0, [self.portal_group.id])],
                }
            )
        )
        domain = self._result_domain(isolated_user)
        self.assertEqual(domain, [("id", "=", False)])
