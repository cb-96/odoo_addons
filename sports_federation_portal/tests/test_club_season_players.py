from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.sports_federation_portal.controllers.club_season_players import (
    FederationClubSeasonPlayersPortal,
)


@tagged("post_install", "-at_install", "sf_season_players")
class TestClubSeasonPlayersPortalScope(TransactionCase):
    def setUp(self):
        super().setUp()
        self.club = self.env["federation.club"].create({"name": "Scoped Annual Club"})
        self.other_club = self.env["federation.club"].create(
            {"name": "Unrelated Annual Club"}
        )
        self.season = self.env["federation.season"].create(
            {
                "name": "Scoped Annual Season",
                "date_start": "2098-01-01",
                "date_end": "2098-12-31",
                "state": "open",
            }
        )
        Registration = self.env["federation.club.season.registration"]
        self.own = Registration._get_or_create(self.club, self.season)
        self.other = Registration._get_or_create(self.other_club, self.season)
        self.controller = FederationClubSeasonPlayersPortal()

    def test_own_registration_available(self):
        with patch(
            "odoo.addons.sports_federation_portal.controllers.club_season_players.request",
            SimpleNamespace(env=self.env),
        ), patch.object(self.controller, "_get_portal_clubs", return_value=self.club):
            self.assertEqual(self.controller._registration(self.own.id), self.own)

    def test_season_player_detail_template_compiles(self):
        self.env["ir.qweb"]._compile(
            "sports_federation_portal.portal_season_players_detail"
        )

    def test_forged_other_club_registration_denied(self):
        with patch(
            "odoo.addons.sports_federation_portal.controllers.club_season_players.request",
            SimpleNamespace(env=self.env),
        ), patch.object(self.controller, "_get_portal_clubs", return_value=self.club):
            with self.assertRaises(AccessError):
                self.controller._registration(self.other.id)
