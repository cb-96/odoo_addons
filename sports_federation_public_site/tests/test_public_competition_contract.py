from pathlib import Path

from odoo.tests.common import TransactionCase


class TestPublicCompetitionContract(TransactionCase):
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

    def test_competition_api_payload_excludes_private_fields(self):
        season = self.env["federation.season"].create(
            {"name": "API season", "date_start": "2026-01-01", "date_end": "2026-12-31"}
        )
        competition = self.env["federation.competition"].create(
            {"name": "API competition", "competition_type": "league"}
        )
        edition = self.env["federation.competition.edition"].create(
            {
                "name": "API edition",
                "competition_id": competition.id,
                "season_id": season.id,
                "state": "open",
                "public_slug": "api-edition",
                "website_published": True,
            }
        )
        payload = edition.get_public_api_payload()
        self.assertEqual(payload["api_version"], "v1")
        self.assertEqual(
            payload["competition"]["api_url"], "/api/v1/competitions/api-edition"
        )
        self.assertEqual(payload["divisions"], [])
        public_data = str(
            {"competition": payload["competition"], "divisions": payload["divisions"]}
        ).lower()
        for private_name in ("email", "phone", "internal_note", "disciplinary_case"):
            self.assertNotIn(private_name, public_data)

    def test_public_division_helpers_use_competition_namespace(self):
        season = self.env["federation.season"].create(
            {
                "name": "Namespace season",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        competition = self.env["federation.competition"].create(
            {"name": "Namespace competition", "competition_type": "league"}
        )
        edition = self.env["federation.competition.edition"].create(
            {
                "name": "Namespace edition",
                "competition_id": competition.id,
                "season_id": season.id,
                "state": "open",
                "public_slug": "namespace-edition",
                "website_published": True,
            }
        )
        division = self.env["federation.tournament"].create(
            {
                "name": "Division A",
                "edition_id": edition.id,
                "date_start": "2026-01-01",
                "website_published": True,
            }
        )
        self.assertEqual(
            division.get_public_path(),
            f"/competitions/namespace-edition?division_id={division.id}",
        )
        self.assertEqual(
            division.get_public_feed_path(), "/api/v1/competitions/namespace-edition"
        )
        self.assertIn(
            "/competitions/namespace-edition/divisions/",
            division.get_public_schedule_ics_path(),
        )

    def test_route_cutover_repairs_stored_hub_inheritance_before_upgrade(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "19.0.3.0.0"
            / "pre-migrate.py"
        ).read_text(encoding="utf-8")
        self.assertIn("page_tournaments_hub_discovery_sections", migration)
        self.assertIn("UPDATE ir_ui_view", migration)
        self.assertIn('_NEW_ACTION = "/competitions"', migration)

    def test_source_defines_no_removed_public_route_namespace(self):
        source_roots = (
            Path(__file__).resolve().parents[1] / "controllers",
            Path(__file__).resolve().parents[1] / "models",
            Path(__file__).resolve().parents[1] / "views",
        )
        removed = ("/" + "tournaments", "/" + "tournament/", "/api/v1/" + "tournaments")
        for source_root in source_roots:
            for path in source_root.rglob("*"):
                if path.suffix not in {".py", ".xml"}:
                    continue
                content = path.read_text(encoding="utf-8")
                for route in removed:
                    self.assertNotIn(
                        route, content, f"Removed route remains in {path}: {route}"
                    )
