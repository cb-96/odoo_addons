from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_season_players")
class TestClubSeasonRegistration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create({"name": "Annual Player Club"})
        cls.other_club = cls.env["federation.club"].create({"name": "Other Annual Club"})
        cls.season = cls.env["federation.season"].create({
            "name": "Annual Player Season", "date_start": "2098-01-01",
            "date_end": "2098-12-31", "state": "open",
        })
        cls.player = cls.env["federation.player"].create({
            "first_name": "Annual", "last_name": "Player", "gender": "male",
            "birth_date": "2000-01-01", "club_id": cls.club.id,
        })
        cls.registration = cls.env["federation.club.season.registration"]._get_or_create(cls.club, cls.season)

    def test_collect_is_draft_and_idempotent(self):
        self.registration.action_collect_club_players()
        self.registration.action_collect_club_players()
        self.assertEqual(len(self.registration.license_ids), 1)
        self.assertEqual(self.registration.license_ids.state, "draft")
        self.assertTrue(self.registration.license_ids.name.startswith("LIC/"))

    def test_submit_approve_and_top_up(self):
        self.registration._add_players(self.player)
        self.registration.action_submit()
        self.registration.action_confirm()
        license = self.registration.license_ids
        self.assertEqual(license.state, "active")
        second = self.player.copy({"first_name": "Second"})
        self.registration._add_players(second)
        self.registration.action_submit()
        self.assertEqual(license.state, "active")
        self.assertEqual(self.registration.pending_player_count, 1)
        self.registration.action_confirm()
        self.assertEqual(self.registration.registered_player_count, 2)

    def test_wrong_club_player_rejected(self):
        self.player.club_id = self.other_club
        with self.assertRaises(ValidationError):
            self.registration._add_players(self.player)

    def test_duplicate_player_rejected(self):
        self.registration._add_players(self.player)
        with self.assertRaises(ValidationError):
            self.registration._add_players(self.player)

    def test_closed_season_rejects_registration(self):
        self.season.state = "closed"
        with self.assertRaises(ValidationError):
            self.registration._add_players(self.player)

    def test_cancel_keeps_history(self):
        self.registration._add_players(self.player)
        self.registration.action_confirm()
        self.registration.action_cancel()
        self.assertEqual(self.registration.license_ids.state, "cancelled")
        with self.assertRaises(ValidationError):
            self.registration.license_ids.unlink()
        with self.assertRaises(ValidationError):
            self.registration.license_ids.write({"club_id": self.other_club.id})

    def test_portal_cannot_approve_directly(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Annual Portal", "login": "annual.portal.test",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        with self.assertRaises(AccessError):
            self.registration.with_user(user).action_confirm()
