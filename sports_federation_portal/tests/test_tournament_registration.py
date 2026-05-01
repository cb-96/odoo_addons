from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestTournamentRegistration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Portal Registration Club",
                "code": "PRC",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Portal Registration Season",
                "code": "PRS",
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
            }
        )
        cls.portal_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.role_type = cls.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )
        cls.eligible_team = cls.env["federation.team"].create(
            {
                "name": "Eligible Portal Team",
                "club_id": cls.club.id,
                "code": "EPT",
                "category": "senior",
                "gender": "male",
            }
        )
        cls.other_club = cls.env["federation.club"].create(
            {
                "name": "Other Portal Registration Club",
                "code": "OPRC",
            }
        )
        cls.other_team = cls.env["federation.team"].create(
            {
                "name": "Other Eligible Portal Team",
                "club_id": cls.other_club.id,
                "code": "OEPT",
                "category": "senior",
                "gender": "male",
            }
        )
        cls.ineligible_team = cls.env["federation.team"].create(
            {
                "name": "Ineligible Portal Team",
                "club_id": cls.club.id,
                "code": "IPT",
                "category": "senior",
                "gender": "female",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Portal Tournament",
                "code": "PT",
                "season_id": cls.season.id,
                "date_start": "2025-06-01",
                "gender": "male",
                "category": "senior",
            }
        )
        cls.user_a = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Portal Registration User A",
                    "login": "portal.registration.a@example.com",
                    "email": "portal.registration.a@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
        cls.user_b = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Portal Registration User B",
                    "login": "portal.registration.b@example.com",
                    "email": "portal.registration.b@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club.id,
                "partner_id": cls.user_a.partner_id.id,
                "user_id": cls.user_a.id,
                "role_type_id": cls.role_type.id,
            }
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.other_club.id,
                "partner_id": cls.user_b.partner_id.id,
                "user_id": cls.user_b.id,
                "role_type_id": cls.role_type.id,
            }
        )

    def test_registration_accepts_eligible_team(self):
        """Test that registration accepts eligible team."""
        registration = self.env["federation.tournament.registration"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": self.eligible_team.id,
            }
        )
        self.assertEqual(registration.team_id, self.eligible_team)

    def test_registration_rejects_ineligible_team(self):
        """Test that registration rejects ineligible team."""
        with self.assertRaises(ValidationError):
            self.env["federation.tournament.registration"].create(
                {
                    "tournament_id": self.tournament.id,
                    "team_id": self.ineligible_team.id,
                }
            )

    def test_registration_backend_domain_uses_eligible_teams(self):
        """Test that registration backend domain uses eligible teams."""
        registration = self.env["federation.tournament.registration"].new(
            {
                "tournament_id": self.tournament.id,
            }
        )
        registration._compute_team_selection()

        eligible_team_ids = registration.eligible_team_ids._origin.ids
        self.assertIn(self.eligible_team.id, eligible_team_ids)
        self.assertNotIn(self.ineligible_team.id, eligible_team_ids)

        available_team_ids = registration.available_team_ids._origin.ids
        self.assertIn(self.eligible_team.id, available_team_ids)
        self.assertNotIn(self.ineligible_team.id, available_team_ids)
        self.assertIn(
            "Ineligible Portal Team", registration.excluded_team_feedback_html
        )

    def test_registration_backend_feedback_explains_duplicate_team(self):
        """Test that registration backend feedback explains duplicate team."""
        self.env["federation.tournament.registration"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": self.eligible_team.id,
                "state": "submitted",
            }
        )

        registration = self.env["federation.tournament.registration"].new(
            {
                "tournament_id": self.tournament.id,
            }
        )
        registration._compute_team_selection()

        self.assertNotIn(
            self.eligible_team.id, registration.available_team_ids._origin.ids
        )
        self.assertIn(
            "Already registered or currently awaiting review.",
            registration.excluded_team_feedback_html,
        )

    def test_portal_user_only_sees_own_tournament_registrations(self):
        """Test that portal user only sees own tournament registrations."""
        own_registration = (
            self.env["federation.tournament.registration"]
            .with_user(self.user_a)
            .create(
                {
                    "tournament_id": self.tournament.id,
                    "team_id": self.eligible_team.id,
                }
            )
        )
        other_registration = (
            self.env["federation.tournament.registration"]
            .with_user(self.user_b)
            .create(
                {
                    "tournament_id": self.tournament.id,
                    "team_id": self.other_team.id,
                }
            )
        )

        visible_to_user_a = (
            self.env["federation.tournament.registration"]
            .with_user(self.user_a)
            .search([])
        )
        self.assertIn(own_registration, visible_to_user_a)
        self.assertNotIn(other_registration, visible_to_user_a)

        with self.assertRaises(AccessError):
            other_registration.with_user(self.user_a).write({"notes": "Not allowed"})

    def test_tournament_action_view_registration_requests(self):
        """Test that tournament action view registration requests."""
        other_tournament = self.env["federation.tournament"].create(
            {
                "name": "Other Portal Tournament",
                "code": "OPT",
                "season_id": self.season.id,
                "date_start": "2025-07-01",
                "gender": "male",
                "category": "senior",
            }
        )
        self.env["federation.tournament.registration"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": self.eligible_team.id,
            }
        )
        self.env["federation.tournament.registration"].create(
            {
                "tournament_id": other_tournament.id,
                "team_id": self.other_team.id,
            }
        )

        self.assertEqual(self.tournament.registration_request_count, 1)

        action = self.tournament.action_view_registration_requests()

        self.assertEqual(
            action["res_model"],
            "federation.tournament.registration",
        )
        self.assertEqual(action["domain"], [("tournament_id", "=", self.tournament.id)])
        self.assertEqual(
            action["context"], {"default_tournament_id": self.tournament.id}
        )

    def test_portal_submit_registration_request_creates_submitted_request(self):
        """Service helper should create and submit a portal tournament request."""
        self.tournament.state = "open"

        registration = self.env[
            "federation.tournament.registration"
        ]._portal_submit_registration_request(
            self.tournament,
            self.eligible_team,
            notes="Submitted through the portal helper.",
            user=self.user_a,
        )

        self.assertEqual(registration.state, "submitted")
        self.assertEqual(registration.create_uid, self.user_a)
        self.assertEqual(registration.notes, "Submitted through the portal helper.")

    def test_portal_submit_registration_request_blocks_full_tournament(self):
        """Service helper should count non-withdrawn participants toward capacity."""
        self.tournament.write({"state": "open", "max_participants": 1})
        self.env["federation.tournament.participant"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": self.other_team.id,
                "state": "registered",
            }
        )

        with self.assertRaises(ValidationError):
            self.env[
                "federation.tournament.registration"
            ]._portal_submit_registration_request(
                self.tournament,
                self.eligible_team,
                user=self.user_a,
            )
