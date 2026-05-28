import re
import unittest

from odoo import SUPERUSER_ID, api
from odoo.addons.sports_federation_base.tests.route_inventory import (
    load_route_inventory,
)
from odoo.tests.common import HttpCase, tagged


def _extract_csrf_token(response_text):
    match = re.search(
        r'name="csrf_token"[^>]*value="([^"]+)"',
        response_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise AssertionError("CSRF token not found in response")
    return match.group(1)


@tagged("-at_install", "post_install")
class TestPublicSiteHttpSmoke(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        with cls.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            portal_club_group = env.ref(
                "sports_federation_portal.group_federation_portal_club",
                raise_if_not_found=False,
            )
            portal_official_group = env.ref(
                "sports_federation_portal.group_federation_portal_official",
                raise_if_not_found=False,
            )
            portal_role_type = env.ref(
                "sports_federation_portal.role_type_competition_contact",
                raise_if_not_found=False,
            )
            if not (portal_club_group and portal_official_group and portal_role_type):
                raise unittest.SkipTest(
                    "sports_federation_portal not installed; skipping HTTP smoke tests"
                )
            season = env["federation.season"].create(
                {
                    "name": "Public Registration Smoke Season",
                    "code": "PRSS",
                    "date_start": "2026-01-01",
                    "date_end": "2026-12-31",
                }
            )
            tournament = env["federation.tournament"].create(
                {
                    "name": "Wrong Role Registration Smoke Tournament",
                    "code": "WRRST",
                    "season_id": season.id,
                    "date_start": "2026-06-01",
                    "state": "open",
                    "website_published": True,
                    "public_slug": "wrong-role-registration-smoke",
                }
            )
            unpublished_tournament = env["federation.tournament"].create(
                {
                    "name": "Hidden Registration Smoke Tournament",
                    "code": "HRST",
                    "season_id": season.id,
                    "date_start": "2026-06-15",
                    "state": "open",
                    "gender": "male",
                    "category": "senior",
                    "website_published": False,
                    "public_slug": "hidden-registration-smoke",
                }
            )
            hidden_season = env["federation.season"].create(
                {
                    "name": "Hidden Public Smoke Season",
                    "code": "HPSS",
                    "date_start": "2027-01-01",
                    "date_end": "2027-12-31",
                    "public_slug": "hidden-public-smoke-season",
                }
            )
            official_user = (
                env["res.users"]
                .with_context(no_reset_password=True)
                .create(
                    {
                        "name": "Wrong Role Registration Smoke User",
                        "login": "wrong.role.registration@example.com",
                        "email": "wrong.role.registration@example.com",
                        "group_ids": [(6, 0, [portal_official_group.id])],
                    }
                )
            )
            club = env["federation.club"].create(
                {
                    "name": "Public Registration Smoke Club",
                    "code": "PRSC",
                }
            )
            club_user = (
                env["res.users"]
                .with_context(no_reset_password=True)
                .create(
                    {
                        "name": "Public Registration Club User",
                        "login": "public.registration.club@example.com",
                        "email": "public.registration.club@example.com",
                        "group_ids": [(6, 0, [portal_club_group.id])],
                    }
                )
            )
            env["federation.club.representative"].create(
                {
                    "club_id": club.id,
                    "partner_id": club_user.partner_id.id,
                    "user_id": club_user.id,
                    "role_type_id": portal_role_type.id,
                }
            )
            eligible_team = env["federation.team"].create(
                {
                    "name": "Public Registration Eligible Team",
                    "club_id": club.id,
                    "code": "PRET",
                    "category": "senior",
                    "gender": "male",
                }
            )
            hidden_team = env["federation.team"].create(
                {
                    "name": "Hidden Follow Smoke Team",
                    "club_id": club.id,
                    "code": "HFST",
                    "category": "senior",
                    "gender": "male",
                    "public_slug": "hidden-follow-smoke-team",
                }
            )
            env["federation.tournament.participant"].create(
                {
                    "tournament_id": unpublished_tournament.id,
                    "team_id": hidden_team.id,
                    "state": "confirmed",
                }
            )
            tournament.write({"gender": "male", "category": "senior"})

            full_tournament = env["federation.tournament"].create(
                {
                    "name": "Full Capacity Smoke Tournament",
                    "code": "FCST",
                    "season_id": season.id,
                    "date_start": "2026-07-01",
                    "state": "open",
                    "gender": "male",
                    "category": "senior",
                    "website_published": True,
                    "public_slug": "full-capacity-smoke",
                    "max_participants": 1,
                }
            )
            full_team = env["federation.team"].create(
                {
                    "name": "Full Capacity Eligible Team",
                    "club_id": club.id,
                    "code": "FCET",
                    "category": "senior",
                    "gender": "male",
                }
            )
            occupied_team = env["federation.team"].create(
                {
                    "name": "Full Capacity Occupied Team",
                    "club_id": club.id,
                    "code": "FCOT",
                    "category": "senior",
                    "gender": "male",
                }
            )
            env["federation.tournament.participant"].create(
                {
                    "tournament_id": full_tournament.id,
                    "team_id": occupied_team.id,
                    "state": "registered",
                }
            )
            cr.commit()

        cls.portal_club_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.portal_official_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_official"
        )
        cls.portal_role_type = cls.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )
        cls.season = cls.env["federation.season"].browse(season.id)
        cls.tournament = cls.env["federation.tournament"].browse(tournament.id)
        cls.unpublished_tournament = cls.env["federation.tournament"].browse(
            unpublished_tournament.id
        )
        cls.hidden_season = cls.env["federation.season"].browse(hidden_season.id)
        cls.official_user = cls.env["res.users"].browse(official_user.id)
        cls.club = cls.env["federation.club"].browse(club.id)
        cls.club_user = cls.env["res.users"].browse(club_user.id)
        cls.eligible_team = cls.env["federation.team"].browse(eligible_team.id)
        cls.hidden_team = cls.env["federation.team"].browse(hidden_team.id)
        cls.full_tournament = cls.env["federation.tournament"].browse(
            full_tournament.id
        )
        cls.full_team = cls.env["federation.team"].browse(full_team.id)
        cls.occupied_team = cls.env["federation.team"].browse(occupied_team.id)

    def test_published_tournament_detail_page_renders(self):
        response = self.url_open(self.tournament.get_public_path())

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.tournament.name, response.text)
        self.assertNotIn("Internal Server Error", response.text)

    def test_unpublished_tournament_detail_routes_fail_closed(self):
        slug_response = self.url_open(
            self.unpublished_tournament.get_public_path(),
            allow_redirects=False,
        )
        numeric_response = self.url_open(
            f"/tournament/{self.unpublished_tournament.id}",
            allow_redirects=False,
        )

        self.assertEqual(slug_response.status_code, 404)
        self.assertEqual(numeric_response.status_code, 404)

    def test_hidden_season_detail_routes_fail_closed(self):
        for path in (
            self.hidden_season.get_public_path(),
            f"/season/{self.hidden_season.id}",
        ):
            response = self.url_open(path, allow_redirects=False)
            self.assertEqual(response.status_code, 404)

    def test_hidden_team_profile_and_follow_routes_fail_closed(self):
        for path in (
            self.hidden_team.get_public_path(),
            self.hidden_team.get_public_schedule_path(),
            self.hidden_team.get_public_results_path(),
            self.hidden_team.get_public_schedule_ics_path(),
            self.hidden_team.get_public_feed_path(),
        ):
            response = self.url_open(path, allow_redirects=False)
            self.assertEqual(response.status_code, 404)

    def test_wrong_role_registration_page_shows_guided_feedback(self):
        self.authenticate(self.official_user.login, "ignored")

        response = self.url_open(self.tournament.get_public_register_path())

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.tournament.name, response.text)
        self.assertIn(
            "You are not registered as a club representative. Please contact the federation.",
            response.text,
        )
        self.assertNotIn("Internal Server Error", response.text)

    def test_representative_registration_submit_shows_success(self):
        self.authenticate(self.club_user.login, "ignored")

        form_response = self.url_open(
            f"/tournament/{self.tournament.id}/register",
            allow_redirects=True,
        )
        self.assertEqual(form_response.status_code, 200)
        self.assertIn(self.eligible_team.name, form_response.text)

        submit_response = self.url_open(
            f"/tournament/{self.tournament.id}/register",
            data={
                "csrf_token": _extract_csrf_token(form_response.text),
                "team_id": str(self.eligible_team.id),
                "notes": "Smoke registration from public site.",
            },
            allow_redirects=True,
        )

        self.assertEqual(submit_response.status_code, 200)
        self.assertIn("Registration submitted successfully", submit_response.text)
        self.assertIn(self.tournament.name, submit_response.text)
        self.assertNotIn("Internal Server Error", submit_response.text)

    def test_unpublished_tournament_register_routes_fail_closed(self):
        self.authenticate(self.club_user.login, "ignored")

        Registration = self.env["federation.tournament.registration"].sudo()
        before_count = Registration.search_count(
            [("tournament_id", "=", self.unpublished_tournament.id)]
        )

        for path in (
            self.unpublished_tournament.get_public_register_path(),
            f"/tournament/{self.unpublished_tournament.id}/register",
        ):
            form_response = self.url_open(path, allow_redirects=False)
            submit_response = self.url_open(
                path,
                data={"team_id": str(self.eligible_team.id)},
                allow_redirects=False,
            )

            self.assertIn(form_response.status_code, (301, 302, 303, 307, 308))
            self.assertTrue(form_response.headers["Location"].endswith("/tournaments"))
            self.assertIn(submit_response.status_code, (301, 302, 303, 307, 308))
            self.assertTrue(
                submit_response.headers["Location"].endswith("/tournaments")
            )

        after_count = Registration.search_count(
            [("tournament_id", "=", self.unpublished_tournament.id)]
        )
        self.assertEqual(after_count, before_count)

    def test_full_tournament_registration_shows_guided_feedback(self):
        self.authenticate(self.club_user.login, "ignored")

        form_response = self.url_open(self.full_tournament.get_public_register_path())
        submit_response = self.url_open(
            self.full_tournament.get_public_register_path(),
            data={
                "csrf_token": _extract_csrf_token(form_response.text),
                "team_id": str(self.full_team.id),
            },
            allow_redirects=True,
        )

        self.assertEqual(submit_response.status_code, 200)
        self.assertIn("Tournament is full", submit_response.text)
        self.assertNotIn("Internal Server Error", submit_response.text)

    def test_route_inventory_lists_smoke_covered_public_routes(self):
        inventory_routes = {
            (entry["method"], entry["path"])
            for entry in load_route_inventory("sports_federation_public_site")
        }

        self.assertEqual(
            inventory_routes,
            {
                ("POST", "/tournaments/<slug>/register"),
            },
        )
