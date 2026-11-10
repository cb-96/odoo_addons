from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged
from ..models.lifecycle import command


@tagged("post_install", "-at_install", "sf_boundaries")
class TestPlayerMembershipBoundary(TransactionCase):
    def setUp(self):
        super().setUp()
        self.club = self.env["federation.club"].create(
            {"name": "Membership Boundary Club"}
        )
        self.season = self.env["federation.season"].create(
            {
                "name": "Membership Boundary Season",
                "date_start": "2098-01-01",
                "date_end": "2098-12-31",
                "state": "open",
            }
        )
        self.person = self.env["res.partner"].create(
            {"name": "Reviewed Boundary Person"}
        )
        self.player = self.env["federation.player"].create(
            {
                "first_name": "Boundary",
                "last_name": "Player",
                "gender": "male",
                "birth_date": "2000-01-01",
                "club_id": self.club.id,
            }
        )
        self.registration = self.env[
            "federation.club.season.registration"
        ]._get_or_create(self.club, self.season)
        self.registration._add_players(self.player)
        self.license = self.registration.license_ids
        # Keep tests independent of configured player fee amounts.
        self.registration.billing_partner_id = self.person

    def membership(self, role="player", **values):
        vals = {
            "person_id": self.person.id,
            "club_id": self.club.id,
            "season_id": self.season.id,
            "role": role,
            "company_id": self.registration.company_id.id,
            "review_note": "Reviewed identity and membership",
        }
        vals.update(values)
        row = self.env["federation.person.membership"].create(vals)
        row.action_activate()
        return row

    def test_optional_membership_does_not_add_second_registration(self):
        self.assertFalse(self.season.player_membership_required)
        self.registration.action_confirm()
        self.assertEqual(self.license.state, "active")
        self.assertEqual(self.license.membership_status, "not_required")
        self.assertFalse(self.player.person_id)

    def test_required_identity_blocks_approval_atomically(self):
        self.season.player_membership_required = True
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.registration.action_confirm()
        self.assertEqual(self.license.state, "draft")

    def test_wrong_role_does_not_satisfy_player_membership(self):
        self.player.person_id = self.person
        self.season.player_membership_required = True
        self.membership(role="coach")
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.registration.action_confirm()

    def test_active_membership_allows_registration_and_revocation_blocks(self):
        self.player.person_id = self.person
        self.season.player_membership_required = True
        membership = self.membership()
        self.registration.action_confirm()
        self.assertEqual(self.license.membership_status, "active")
        team = self.env["federation.team"].create(
            {"name": "Boundary Team", "club_id": self.club.id}
        )
        roster = self.env["federation.team.roster"].create(
            {"team_id": team.id, "season_id": self.season.id}
        )
        line = self.env["federation.team.roster.line"].create(
            {"roster_id": roster.id, "player_id": self.player.id}
        )
        self.assertTrue(line.eligible)
        # Exercise the same command-owned write used by reviewed lifecycle actions.
        command(membership).write({"state": "cancelled"})
        self.assertFalse(line.eligible)
        self.assertEqual(self.license.state, "active")
        self.assertNotIn(
            self.player,
            self.env["federation.player.license"]._registered_players(
                self.club,
                self.season,
                fields.Date.to_date("2098-06-01"),
            ),
        )

    def test_wrong_club_membership_blocks(self):
        self.player.person_id = self.person
        self.season.player_membership_required = True
        other = self.env["federation.club"].create({"name": "Other Membership Club"})
        self.membership(club_id=other.id)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.registration.action_confirm()

    def test_membership_review_action_has_exact_scope(self):
        self.player.person_id = self.person
        action = self.license.action_review_membership()
        self.assertEqual(action["context"]["default_person_id"], self.person.id)
        self.assertEqual(action["context"]["default_role"], "player")
        self.assertIn(
            ("company_id", "=", self.registration.company_id.id), action["domain"]
        )

    def test_wrong_season_membership_blocks(self):
        self.player.person_id = self.person
        self.season.player_membership_required = True
        other = self.env["federation.season"].create(
            {
                "name": "Other Membership Season",
                "date_start": "2099-01-01",
                "date_end": "2099-12-31",
                "state": "open",
            }
        )
        self.membership(season_id=other.id)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.registration.action_confirm()

    def test_membership_alone_does_not_approve_player(self):
        self.player.person_id = self.person
        self.season.player_membership_required = True
        self.membership()
        self.assertEqual(self.license.state, "draft")
        self.assertNotIn(
            self.player,
            self.env["federation.player.license"]._registered_players(
                self.club,
                self.season,
                fields.Date.to_date("2098-06-01"),
            ),
        )
