"""Portal users reach records through the ORM only inside their own scope.

Portal pages filter their data, but a logged-in portal user can also call the
ORM directly (``/web/dataset/call_kw``). These tests act as such a user: they
use ``with_user`` on the models and never go through ``portal.privilege``.
"""

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_portal_isolation")
class TestPortalOrmIsolation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.club_group = env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.role = env.ref("sports_federation_portal.role_type_competition_contact")
        cls.team_role = env["federation.club.role.type"].create(
            {
                "name": "Isolation team role",
                "code": "isolation_team_role",
                "team_scoped": True,
            }
        )
        cls.club_a = env["federation.club"].create({"name": "Isolation Club A"})
        cls.club_b = env["federation.club"].create({"name": "Isolation Club B"})
        cls.team_a1 = env["federation.team"].create(
            {"name": "Isolation A1", "club_id": cls.club_a.id}
        )
        cls.team_a2 = env["federation.team"].create(
            {"name": "Isolation A2", "club_id": cls.club_a.id}
        )
        cls.team_b1 = env["federation.team"].create(
            {"name": "Isolation B1", "club_id": cls.club_b.id}
        )
        cls.season = env["federation.season"].create(
            {
                "name": "Isolation Season",
                "code": "ISO",
                "date_start": "2090-01-01",
                "date_end": "2090-12-31",
            }
        )
        Player = env["federation.player"]
        cls.player_a1 = Player.create(
            {
                "first_name": "Ann",
                "last_name": "One",
                "club_id": cls.club_a.id,
                "team_ids": [(6, 0, cls.team_a1.ids)],
                "email": "ann@example.com",
            }
        )
        cls.player_a2 = Player.create(
            {
                "first_name": "Ann",
                "last_name": "Two",
                "club_id": cls.club_a.id,
                "team_ids": [(6, 0, cls.team_a2.ids)],
            }
        )
        cls.player_b = Player.create(
            {
                "first_name": "Ben",
                "last_name": "Other",
                "club_id": cls.club_b.id,
                "birth_date": "2012-03-04",
                "email": "ben@example.com",
                "phone": "+32 000 00 00 00",
            }
        )
        cls.reg_a1 = env["federation.season.registration"].create(
            {"team_id": cls.team_a1.id, "season_id": cls.season.id}
        )
        cls.reg_a2 = env["federation.season.registration"].create(
            {"team_id": cls.team_a2.id, "season_id": cls.season.id}
        )
        cls.reg_b = env["federation.season.registration"].create(
            {"team_id": cls.team_b1.id, "season_id": cls.season.id}
        )
        cls.rep_a = cls._portal_user("Rep A", "iso.rep.a", cls.club_a)
        cls.rep_b = cls._portal_user("Rep B", "iso.rep.b", cls.club_b)
        cls.coach_a1 = cls._portal_user(
            "Coach A1", "iso.coach.a1", cls.club_a, team=cls.team_a1
        )

    @classmethod
    def _portal_user(cls, name, login, club, team=None):
        user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": name,
                    "login": login + "@example.com",
                    "email": login + "@example.com",
                    "group_ids": [(6, 0, [cls.club_group.id])],
                }
            )
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": club.id,
                "partner_id": user.partner_id.id,
                "user_id": user.id,
                "role_type_id": (cls.team_role if team else cls.role).id,
                "team_id": team.id if team else False,
            }
        )
        return user

    # -- players ----------------------------------------------------------

    def test_representative_sees_only_own_club_players(self):
        players = self.env["federation.player"].with_user(self.rep_a).search([])
        self.assertEqual(players, self.player_a1 | self.player_a2)

    def test_other_clubs_player_cannot_be_read_or_browsed(self):
        as_a = self.env["federation.player"].with_user(self.rep_a)
        with self.assertRaises(AccessError):
            as_a.browse(self.player_b.id).read(["first_name", "email", "birth_date"])
        with self.assertRaises(AccessError):
            as_a.browse(self.player_b.id).mapped("email")

    def test_players_cannot_be_created_through_the_orm(self):
        with self.assertRaises(AccessError):
            self.env["federation.player"].with_user(self.rep_a).create(
                {"first_name": "Mallory", "last_name": "New", "club_id": self.club_a.id}
            )

    def test_team_coach_sees_only_the_players_of_their_team(self):
        players = self.env["federation.player"].with_user(self.coach_a1).search([])
        self.assertEqual(players, self.player_a1)

    # -- season registrations, participants, clubs -------------------------

    def test_registrations_follow_the_same_scope(self):
        Registration = self.env["federation.season.registration"]
        self.assertEqual(
            Registration.with_user(self.rep_a).search([]), self.reg_a1 | self.reg_a2
        )
        self.assertEqual(Registration.with_user(self.rep_b).search([]), self.reg_b)

    def test_team_coach_cannot_touch_other_teams_of_the_club(self):
        Registration = self.env["federation.season.registration"].with_user(
            self.coach_a1
        )
        self.assertEqual(Registration.search([]), self.reg_a1)
        with self.assertRaises(AccessError):
            Registration.browse(self.reg_a2.id).write({"notes": "club-wide edit"})

    def test_club_rule_follows_current_scope(self):
        Club = self.env["federation.club"]
        self.assertEqual(Club.with_user(self.rep_a).search([]), self.club_a)
        self.assertEqual(Club.with_user(self.coach_a1).search([]), self.club_a)
        self.assertEqual(Club.with_user(self.rep_b).search([]), self.club_b)

    # -- referee duties -----------------------------------------------------

    def test_referee_duties_are_not_open_to_every_portal_user(self):
        """Match officials are portal users too; duties belong to clubs only."""
        official = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Isolation Official",
                    "login": "iso.official@example.com",
                    "group_ids": [
                        (
                            6,
                            0,
                            [
                                self.env.ref(
                                    "sports_federation_portal.group_federation_portal_official"
                                ).id
                            ],
                        )
                    ],
                }
            )
        )
        Duty = self.env["federation.match.club.referee.duty"]
        with self.assertRaises(AccessError):
            Duty.with_user(official).check_access("read")
        Duty.with_user(self.rep_a).check_access("read")

    # -- every portal ACL is backed by a record rule -------------------------

    def test_every_portal_access_right_has_a_record_rule(self):
        """Database counterpart of ci/check_portal_record_rules.py."""
        portal_groups = (
            self.club_group
            | self.env.ref("sports_federation_portal.group_federation_portal_official")
            | self.env.ref("base.group_portal")
        )
        Access = self.env["ir.model.access"].sudo()
        Rule = self.env["ir.rule"].sudo()
        unscoped = []
        for access in Access.search([("group_id", "in", portal_groups.ids)]):
            if not access.model_id.model.startswith("federation."):
                continue
            if not (access.perm_read or access.perm_write or access.perm_create):
                continue
            rules = Rule.search([("model_id", "=", access.model_id.id)])
            covering = rules.filtered(
                lambda rule: not rule.groups or access.group_id in rule.groups
            )
            if not covering:
                unscoped.append(access.model_id.model)
        # Seasons are public data (also on the public site) and read only.
        self.assertEqual(sorted(unscoped), ["federation.season"])

    # -- tenure ends by date ----------------------------------------------

    def test_ended_tenure_loses_access_after_the_refresh_job(self):
        today = fields.Date.context_today(self.env["federation.club.representative"])
        self.env["federation.club.representative"].search(
            [("user_id", "=", self.rep_a.id)]
        ).write({"date_end": today})
        Player = self.env["federation.player"]
        self.assertTrue(Player.with_user(self.rep_a).search([]))

        tomorrow = today + timedelta(days=1)
        self._refresh_on(tomorrow)

        self.assertFalse(Player.with_user(self.rep_a).search([]))
        with self.assertRaises(AccessError):
            Player.with_user(self.rep_a).browse(self.player_a1.id).read(["first_name"])

    def test_future_tenure_gains_access_after_the_refresh_job(self):
        Rep = self.env["federation.club.representative"]
        start = fields.Date.context_today(Rep) + timedelta(days=3)
        Rep.search([("user_id", "=", self.rep_a.id)]).write({"date_start": start})
        Player = self.env["federation.player"]
        self.assertFalse(Player.with_user(self.rep_a).search([]))

        self._refresh_on(start)

        self.assertEqual(
            Player.with_user(self.rep_a).search([]), self.player_a1 | self.player_a2
        )

    def _refresh_on(self, day):
        """Run the hourly refresh job as if ``day`` had come."""
        with patch("odoo.fields.Date.context_today", return_value=day):
            self.env["federation.club.representative"]._cron_refresh_time_based_state()
        self.env.invalidate_all()
