from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestOfficiatingPortalAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.portal_official_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_official"
        )
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Portal Official Club",
                "code": "POC",
            }
        )
        cls.home_team = cls.env["federation.team"].create(
            {
                "name": "Portal Official Home",
                "club_id": cls.club.id,
                "code": "POH",
            }
        )
        cls.away_team = cls.env["federation.team"].create(
            {
                "name": "Portal Official Away",
                "club_id": cls.club.id,
                "code": "POA",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Portal Official Season",
                "code": "POS",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Portal Official Tournament",
                "code": "POT",
                "season_id": cls.season.id,
                "date_start": "2026-06-01",
            }
        )
        cls.match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.home_team.id,
                "away_team_id": cls.away_team.id,
                "date_scheduled": "2026-06-15 18:00:00",
            }
        )
        cls.other_match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.away_team.id,
                "away_team_id": cls.home_team.id,
                "date_scheduled": "2026-06-21 14:00:00",
            }
        )
        cls.official_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Portal Official User",
                    "login": "portal.official@example.com",
                    "email": "portal.official@example.com",
                    "group_ids": [(6, 0, [cls.portal_official_group.id])],
                }
            )
        )
        cls.other_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Other Official User",
                    "login": "portal.other.official@example.com",
                    "email": "portal.other.official@example.com",
                    "group_ids": [(6, 0, [cls.portal_official_group.id])],
                }
            )
        )
        cls.referee = cls.env["federation.referee"].create(
            {
                "name": "Portal Referee",
                "email": "portal.official@example.com",
                "certification_level": "national",
                "user_id": cls.official_user.id,
            }
        )
        cls.other_referee = cls.env["federation.referee"].create(
            {
                "name": "Other Portal Referee",
                "email": "portal.other.official@example.com",
                "certification_level": "regional",
                "user_id": cls.other_user.id,
            }
        )
        cls.assignment = cls.env["federation.match.referee"].create(
            {
                "match_id": cls.match.id,
                "referee_id": cls.referee.id,
                "role": "head",
            }
        )
        cls.other_assignment = cls.env["federation.match.referee"].create(
            {
                "match_id": cls.other_match.id,
                "referee_id": cls.other_referee.id,
                "role": "assistant_1",
            }
        )

    def test_portal_referee_profile_resolves_for_user(self):
        """Test that portal referee profile resolves for user."""
        profile = self.env["federation.referee"]._portal_get_for_user(
            user=self.official_user
        )
        self.assertEqual(profile, self.referee)

    def test_portal_official_only_sees_own_assignments(self):
        """Test that portal official only sees own assignments."""
        visible_assignments = (
            self.env["federation.match.referee"]
            .with_user(self.official_user)
            .search([])
        )
        self.assertIn(self.assignment, visible_assignments)
        self.assertNotIn(self.other_assignment, visible_assignments)

    def test_portal_official_can_confirm_assignment(self):
        """Test that portal official can confirm assignment."""
        self.assignment._portal_action_confirm(
            user=self.official_user,
            response_note="Confirmed through portal.",
        )
        self.assignment.invalidate_recordset()
        self.assertEqual(self.assignment.state, "confirmed")
        self.assertEqual(self.assignment.response_note, "Confirmed through portal.")

    def test_portal_official_decline_requires_reason(self):
        """Test that portal official decline requires reason."""
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.other_match.id,
                "referee_id": self.referee.id,
                "role": "assistant_2",
            }
        )
        with self.assertRaises(ValidationError):
            assignment._portal_action_decline(user=self.official_user, response_note="")

        assignment._portal_action_decline(
            user=self.official_user,
            response_note="Unavailable due to travel.",
        )
        assignment.invalidate_recordset()
        self.assertEqual(assignment.state, "cancelled")
        self.assertEqual(assignment.response_note, "Unavailable due to travel.")

    def test_other_user_cannot_manage_assignment(self):
        """Test that other user cannot manage assignment."""
        with self.assertRaises(AccessError):
            self.assignment._portal_action_confirm(user=self.other_user)
