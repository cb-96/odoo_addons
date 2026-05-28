from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestPlayerPortalAccess(TransactionCase):
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
                "name": "Portal Player Club",
                "code": "PPC",
            }
        )
        cls.other_club = cls.env["federation.club"].create(
            {
                "name": "Other Portal Player Club",
                "code": "OPPC",
            }
        )
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Portal Player User",
                    "login": "portal.player.user@example.com",
                    "email": "portal.player.user@example.com",
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

    def test_portal_create_player_success(self):
        """Club representative can add a new player to their own club."""
        player = self.env["federation.player"]._portal_create_player(
            self.club,
            values={
                "first_name": "Alice",
                "last_name": "Smith",
                "birth_date": "2000-05-15",
                "gender": "female",
                "email": "alice.smith@example.com",
            },
            user=self.user,
        )

        self.assertEqual(player.first_name, "Alice")
        self.assertEqual(player.last_name, "Smith")
        self.assertEqual(player.club_id, self.club)
        self.assertEqual(player.gender, "female")
        self.assertEqual(player.email, "alice.smith@example.com")
        self.assertEqual(player.create_uid, self.user)

    def test_portal_create_player_audit_trail(self):
        """Player creation through the portal boundary produces an audit row."""
        player = self.env["federation.player"]._portal_create_player(
            self.club,
            values={
                "first_name": "Bob",
                "last_name": "Jones",
            },
            user=self.user,
        )

        audit_event = self.env["federation.audit.event"].search(
            [
                ("event_family", "=", "portal_privilege"),
                ("event_type", "=", "portal_create"),
                ("target_model", "=", "federation.player"),
                ("target_res_id", "=", player.id),
            ],
            limit=1,
        )
        self.assertTrue(audit_event)
        self.assertEqual(audit_event.actor_user_id, self.user)

    def test_portal_create_player_blocks_other_club(self):
        """Club representative cannot add players to a club they don't represent."""
        with self.assertRaises(AccessError):
            self.env["federation.player"]._portal_create_player(
                self.other_club,
                values={
                    "first_name": "Charlie",
                    "last_name": "Brown",
                },
                user=self.user,
            )

    def test_portal_create_player_requires_first_name(self):
        """Player creation fails without a first name."""
        with self.assertRaises(ValidationError):
            self.env["federation.player"]._portal_create_player(
                self.club,
                values={
                    "first_name": "",
                    "last_name": "NoFirstName",
                },
                user=self.user,
            )

    def test_portal_create_player_requires_last_name(self):
        """Player creation fails without a last name."""
        with self.assertRaises(ValidationError):
            self.env["federation.player"]._portal_create_player(
                self.club,
                values={
                    "first_name": "NoLastName",
                    "last_name": "",
                },
                user=self.user,
            )

    def test_portal_create_player_minimal_fields(self):
        """Player creation succeeds with only first and last name supplied."""
        player = self.env["federation.player"]._portal_create_player(
            self.club,
            values={
                "first_name": "Min",
                "last_name": "Imal",
            },
            user=self.user,
        )
        self.assertTrue(player.id)
        self.assertEqual(player.club_id, self.club)
        self.assertFalse(player.birth_date)
        self.assertFalse(player.gender)
