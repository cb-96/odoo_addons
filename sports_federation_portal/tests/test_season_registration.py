from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestSeasonRegistrationOwnership(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.portal_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.role_type = cls.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )

        cls.club = cls.env["federation.club"].create(
            {
                "name": "Season Portal Club",
                "code": "SPC",
            }
        )
        cls.other_club = cls.env["federation.club"].create(
            {
                "name": "Other Portal Club",
                "code": "OPC",
            }
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Season Portal Team",
                "club_id": cls.club.id,
                "code": "SPT",
            }
        )
        cls.other_team = cls.env["federation.team"].create(
            {
                "name": "Other Portal Team",
                "club_id": cls.other_club.id,
                "code": "OPT",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Portal Season",
                "code": "PSEASON",
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
            }
        )
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Season Portal User",
                    "login": "season.portal.user@example.com",
                    "email": "season.portal.user@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club.id,
                "partner_id": cls.user.partner_id.id,
                "user_id": cls.user.id,
                "role_type_id": cls.role_type.id,
            }
        )

    def test_portal_user_can_create_owned_season_registration(self):
        """Test that portal user can create owned season registration."""
        registration = (
            self.env["federation.season.registration"]
            .with_user(self.user)
            .create(
                {
                    "season_id": self.season.id,
                    "team_id": self.team.id,
                }
            )
        )

        self.assertEqual(registration.club_id, self.club)
        registration.action_submit()
        self.assertEqual(registration.state, "submitted")

    def test_portal_user_cannot_create_other_club_registration(self):
        """Test that portal user cannot create other club registration."""
        with self.assertRaises(ValidationError):
            self.env["federation.season.registration"].with_user(self.user).create(
                {
                    "season_id": self.season.id,
                    "team_id": self.other_team.id,
                }
            )

    def test_submitted_registration_can_be_confirmed_by_staff(self):
        """Test that submitted registration can be confirmed by staff."""
        registration = (
            self.env["federation.season.registration"]
            .with_user(self.user)
            .create(
                {
                    "season_id": self.season.id,
                    "team_id": self.team.id,
                }
            )
        )

        registration.action_submit()
        self.assertEqual(registration.state, "submitted")
        self.assertEqual(registration.user_id, self.user)
        self.assertEqual(registration.partner_id, self.user.partner_id)

        registration.action_confirm()
        self.assertEqual(registration.state, "confirmed")

    def test_portal_submit_registration_request_uses_service_boundary(self):
        """Service helper should create and submit a portal season registration."""
        self.season.state = "open"
        registration = self.env[
            "federation.season.registration"
        ]._portal_submit_registration_request(
            self.season,
            self.team,
            notes="Submitted through the portal helper.",
            user=self.user,
        )

        self.assertEqual(registration.state, "submitted")
        self.assertEqual(registration.create_uid, self.user)
        self.assertEqual(registration.notes, "Submitted through the portal helper.")

        audit_events = self.env["federation.audit.event"].search(
            [
                ("event_family", "=", "portal_privilege"),
                ("target_model", "=", "federation.season.registration"),
                ("target_res_id", "=", registration.id),
            ],
            order="event_on asc, id asc",
        )
        self.assertEqual(
            audit_events.mapped("event_type"), ["portal_create", "portal_call"]
        )
        self.assertEqual(
            [event.actor_user_id.id for event in audit_events],
            [self.user.id, self.user.id],
        )
        self.assertEqual(audit_events[-1].action_name, "action_submit")

    def test_portal_submit_registration_request_blocks_unowned_team(self):
        """Service helper should reject season registrations for other clubs."""
        self.season.state = "open"
        with self.assertRaises(AccessError):
            self.env[
                "federation.season.registration"
            ]._portal_submit_registration_request(
                self.season,
                self.other_team,
                user=self.user,
            )
