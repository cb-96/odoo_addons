from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestTeamPortalAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.role_type = cls.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )

        cls.club = cls.env["federation.club"].create(
            {
                "name": "Portal Team Club",
                "code": "PTC",
            }
        )
        cls.other_club = cls.env["federation.club"].create(
            {
                "name": "Other Portal Team Club",
                "code": "OPTC",
            }
        )
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Portal Team User",
                    "login": "portal.team.user@example.com",
                    "email": "portal.team.user@example.com",
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

    def test_portal_create_team_preserves_request_user(self):
        """Portal team helper should create club-owned teams for the portal user."""
        team = self.env["federation.team"]._portal_create_team(
            self.club,
            values={
                "name": "Portal Smoke Team",
                "category": "senior",
                "gender": "male",
                "email": "team@example.com",
            },
            user=self.user,
        )

        self.assertEqual(team.club_id, self.club)
        self.assertEqual(team.create_uid, self.user)
        self.assertEqual(team.email, "team@example.com")

        audit_event = self.env["federation.audit.event"].search(
            [
                ("event_family", "=", "portal_privilege"),
                ("event_type", "=", "portal_create"),
                ("target_model", "=", "federation.team"),
                ("target_res_id", "=", team.id),
            ],
            limit=1,
        )
        self.assertTrue(audit_event)
        self.assertEqual(audit_event.actor_user_id, self.user)
        self.assertEqual(audit_event.action_name, "create")
        self.assertIn("category", audit_event.changed_fields)

    def test_portal_create_team_blocks_other_club(self):
        """Portal team helper should reject unowned clubs."""
        with self.assertRaises(AccessError):
            self.env["federation.team"]._portal_create_team(
                self.other_club,
                values={
                    "name": "Blocked Portal Team",
                    "category": "senior",
                    "gender": "male",
                },
                user=self.user,
            )
