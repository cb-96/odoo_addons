"""
Smoke tests for Phase 2: public club and team profile pages.

Asserts:
  - /clubs returns HTTP 200
  - An unpublished club does NOT appear in the /clubs listing
  - A published club appears on /clubs and its detail slug returns HTTP 200
  - An unpublished club's slug returns HTTP 404
"""

from odoo import SUPERUSER_ID, api
from odoo.tests.common import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestClubPublicPages(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        with cls.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})

            cls.pub_club_id = (
                env["federation.club"]
                .create(
                    {
                        "name": "Public Club Page Smoke Club",
                        "code": "PCPSC",
                        "website_published": True,
                        "public_slug": "public-club-page-smoke",
                    }
                )
                .id
            )

            cls.hidden_club_id = (
                env["federation.club"]
                .create(
                    {
                        "name": "Hidden Club Page Smoke Club",
                        "code": "HCPSC",
                        "website_published": False,
                        "public_slug": "hidden-club-page-smoke",
                    }
                )
                .id
            )

    def test_clubs_list_returns_200(self):
        res = self.url_open("/clubs")
        self.assertEqual(res.status_code, 200)

    def test_published_club_appears_in_list(self):
        res = self.url_open("/clubs")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Public Club Page Smoke Club", res.text)

    def test_unpublished_club_not_in_list(self):
        res = self.url_open("/clubs")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("Hidden Club Page Smoke Club", res.text)

    def test_published_club_detail_returns_200(self):
        res = self.url_open("/clubs/public-club-page-smoke")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Public Club Page Smoke Club", res.text)

    def test_unpublished_club_detail_returns_404(self):
        res = self.url_open("/clubs/hidden-club-page-smoke")
        self.assertEqual(res.status_code, 404)
