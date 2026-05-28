"""
Smoke tests for Phase 2: public player profile pages.

Asserts:
  - /players returns HTTP 200
  - A public_visible=True player appears in the listing and via their slug
  - A public_visible=False player does NOT appear in the listing or via slug
"""
from odoo import SUPERUSER_ID, api
from odoo.tests.common import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestPlayerPublicPages(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        with cls.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})

            cls.pub_player_id = env["federation.player"].create(
                {
                    "first_name": "PlayerSmoke",
                    "last_name": "Public",
                    "public_visible": True,
                    "public_slug": "player-smoke-public",
                }
            ).id

            cls.hidden_player_id = env["federation.player"].create(
                {
                    "first_name": "PlayerSmoke",
                    "last_name": "Hidden",
                    "public_visible": False,
                    "public_slug": "player-smoke-hidden",
                }
            ).id

    def test_players_list_returns_200(self):
        res = self.url_open("/players")
        self.assertEqual(res.status_code, 200)

    def test_public_player_appears_in_list(self):
        res = self.url_open("/players")
        self.assertEqual(res.status_code, 200)
        self.assertIn("PlayerSmoke", res.text)

    def test_hidden_player_not_in_list(self):
        res = self.url_open("/players")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("player-smoke-hidden", res.text)

    def test_public_player_detail_returns_200(self):
        res = self.url_open("/players/player-smoke-public")
        self.assertEqual(res.status_code, 200)
        self.assertIn("PlayerSmoke", res.text)

    def test_hidden_player_detail_returns_404(self):
        res = self.url_open("/players/player-smoke-hidden")
        self.assertEqual(res.status_code, 404)
