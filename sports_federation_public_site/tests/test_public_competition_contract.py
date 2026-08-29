from odoo.tests.common import TransactionCase


class TestPublicCompetitionContract(TransactionCase):
    def test_legacy_division_is_not_public(self):
        legacy = self.env["federation.tournament"].create(
            {
                "name": "Legacy test",
                "date_start": "2026-08-23",
                "website_published": True,
            }
        )
        editions = self.env["federation.public.competition.queries"].list_editions()
        self.assertNotIn(legacy, editions.mapped("tournament_ids"))

    def test_unpublished_edition_hides_published_child(self):
        season = self.env["federation.season"].create(
            {
                "name": "Portal contract season",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        competition = self.env["federation.competition"].create(
            {"name": "Portal contract", "competition_type": "league"}
        )
        edition = self.env["federation.competition.edition"].create(
            {
                "name": "Portal contract edition",
                "competition_id": competition.id,
                "season_id": season.id,
                "state": "open",
                "public_slug": "portal-contract",
                "website_published": False,
            }
        )
        self.assertFalse(
            self.env["federation.public.competition.queries"].resolve_edition(
                edition.public_slug
            )
        )
