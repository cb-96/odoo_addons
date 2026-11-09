from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_player_availability")
class TestPlayerAvailabilityPortal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {"name": "Portal Availability Club", "code": "PAV"}
        )
        cls.other_club = cls.env["federation.club"].create(
            {
                "name": "Portal Availability Rivals",
                "code": "PAR",
                "player_availability_enabled": True,
            }
        )
        cls.other_team = cls.env["federation.team"].create(
            {"name": "Portal Availability Rival Team", "club_id": cls.other_club.id}
        )
        group = cls.env.ref("sports_federation_portal.group_federation_portal_club")
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Availability Representative",
                    "login": "availability.rep@example.com",
                    "group_ids": [(6, 0, [group.id])],
                }
            )
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club.id,
                "partner_id": cls.user.partner_id.id,
                "user_id": cls.user.id,
                "role_type_id": cls.env.ref(
                    "sports_federation_portal.role_type_competition_contact"
                ).id,
            }
        )
        cls.Request = cls.env["federation.player.availability.request"]

    def test_representative_switches_own_club_only(self):
        Club = self.env["federation.club"]
        Club._portal_set_player_availability(self.club.id, True, user=self.user)
        self.assertTrue(self.club.player_availability_enabled)
        Club._portal_set_player_availability(self.club.id, False, user=self.user)
        self.assertFalse(self.club.player_availability_enabled)
        with self.assertRaises(AccessError):
            Club._portal_set_player_availability(self.other_club.id, False, user=self.user)
        self.assertTrue(self.other_club.player_availability_enabled)

    def test_disabled_club_has_no_teams_in_availability(self):
        self.assertFalse(self.Request._portal_enabled(user=self.user))
        self.assertEqual(self.Request._portal_upcoming(user=self.user), [])

    def test_other_clubs_requests_are_not_reachable(self):
        season = self.env["federation.season"].create(
            {
                "name": "Rival Season",
                "code": "RVS",
                "date_start": "2098-09-01",
                "date_end": "2099-06-30",
            }
        )
        competition = self.env["federation.competition"].create(
            {"name": "Rival Competition", "competition_type": "league"}
        )
        edition = self.env["federation.competition.edition"].create(
            {
                "name": "Rival Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        day = self.env["federation.matchday"].create(
            {
                "name": "Rival Day",
                "edition_id": edition.id,
                "date": "2099-01-01",
                "venue_id": self.env["federation.venue"].create({"name": "Rival Venue"}).id,
            }
        )
        request = self.Request.create(
            {"team_id": self.other_team.id, "matchday_id": day.id}
        )
        with self.assertRaises(AccessError):
            self.Request._portal_get(request.id, user=self.user)
        with self.assertRaises(AccessError):
            self.Request._portal_create(self.other_team.id, day.id, user=self.user)
