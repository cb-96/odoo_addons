from odoo.tests.common import HttpCase, tagged


@tagged("-at_install", "post_install", "sf_browser_public_site")
class TestBrowserPublicSite(HttpCase):
    """Exercise the anonymous public-site navigation and route cutover."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Browser Public Season",
                "code": "BPS26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.competition = cls.env["federation.competition"].create(
            {
                "name": "Browser Public Competition",
                "competition_type": "league",
            }
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Browser Public Competition",
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
                "engine_state": "active",
                "public_slug": "browser-public-competition",
                "public_summary": "Browser validation of the public competition experience.",
                "website_published": True,
            }
        )
        cls.division = cls.env["federation.tournament"].create(
            {
                "name": "Open Division",
                "edition_id": cls.edition.id,
                "date_start": "2026-04-01",
                "date_end": "2026-06-30",
                "website_published": True,
            }
        )

    def test_public_site_browser_lifecycle(self):
        self.start_tour(
            "/competitions",
            "public_site_browser_lifecycle",
            login=None,
            timeout=180,
        )
