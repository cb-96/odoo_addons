import re
from urllib.parse import parse_qs, urlparse

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
class TestPortalHttpSmoke(HttpCase):
    def test_web_login_get_renders_login_page(self):
        response = self.url_open("/web/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn('name="login"', response.text)
        self.assertNotIn("Internal Server Error", response.text)

    def test_web_login_recovers_from_stale_csrf_submission(self):
        login = "portal.login.smoke@example.com"

        response = self.url_open(
            "/web/login",
            data={
                "login": login,
                "password": "ignored",
                "csrf_token": "stale-token",
            },
            allow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)

        location = urlparse(response.url)
        query = parse_qs(location.query)

        self.assertEqual(location.path, "/web/login")
        self.assertEqual(query.get("session_expired"), ["1"])
        self.assertEqual(query.get("login"), [login])
        self.assertIn(
            "Your session expired. Please sign in again and retry your last action.",
            response.text,
        )
        self.assertIn(login, response.text)


@tagged("-at_install", "post_install")
class TestPortalWorkflowHttpSmoke(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        with cls.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            portal_club_group = env.ref(
                "sports_federation_portal.group_federation_portal_club"
            )
            portal_official_group = env.ref(
                "sports_federation_portal.group_federation_portal_official"
            )
            portal_role_type = env.ref(
                "sports_federation_portal.role_type_competition_contact"
            )

            team_club = env["federation.club"].create(
                {
                    "name": "Portal Team Smoke Club",
                    "code": "PTSC",
                }
            )
            team_user = (
                env["res.users"]
                .with_context(no_reset_password=True)
                .create(
                    {
                        "name": "Portal Team Smoke User",
                        "login": "portal.team.smoke@example.com",
                        "email": "portal.team.smoke@example.com",
                        "group_ids": [(6, 0, [portal_club_group.id])],
                    }
                )
            )
            env["federation.club.representative"].create(
                {
                    "club_id": team_club.id,
                    "partner_id": team_user.partner_id.id,
                    "user_id": team_user.id,
                    "role_type_id": portal_role_type.id,
                }
            )

            season_club = env["federation.club"].create(
                {
                    "name": "Portal Season Smoke Club",
                    "code": "PSSC",
                }
            )
            season_user = (
                env["res.users"]
                .with_context(no_reset_password=True)
                .create(
                    {
                        "name": "Portal Season Smoke User",
                        "login": "portal.season.smoke@example.com",
                        "email": "portal.season.smoke@example.com",
                        "group_ids": [(6, 0, [portal_club_group.id])],
                    }
                )
            )
            env["federation.club.representative"].create(
                {
                    "club_id": season_club.id,
                    "partner_id": season_user.partner_id.id,
                    "user_id": season_user.id,
                    "role_type_id": portal_role_type.id,
                }
            )
            season_team = env["federation.team"].create(
                {
                    "name": "Portal Season Smoke Team",
                    "club_id": season_club.id,
                    "code": "PSST",
                    "category": "senior",
                    "gender": "male",
                }
            )
            open_season = env["federation.season"].create(
                {
                    "name": "Portal Smoke Season",
                    "code": "PSS",
                    "date_start": "2026-01-01",
                    "date_end": "2026-12-31",
                    "state": "open",
                }
            )

            officiating_club = env["federation.club"].create(
                {
                    "name": "Portal Officiating Smoke Club",
                    "code": "POSC",
                }
            )
            home_team = env["federation.team"].create(
                {
                    "name": "Portal Officiating Home",
                    "club_id": officiating_club.id,
                    "code": "POH",
                }
            )
            away_team = env["federation.team"].create(
                {
                    "name": "Portal Officiating Away",
                    "club_id": officiating_club.id,
                    "code": "POA",
                }
            )
            officiating_season = env["federation.season"].create(
                {
                    "name": "Portal Officiating Smoke Season",
                    "code": "POSS",
                    "date_start": "2026-01-01",
                    "date_end": "2026-12-31",
                }
            )
            officiating_tournament = env["federation.tournament"].create(
                {
                    "name": "Portal Officiating Smoke Tournament",
                    "code": "POST",
                    "season_id": officiating_season.id,
                    "date_start": "2026-06-01",
                }
            )
            official_user = (
                env["res.users"]
                .with_context(no_reset_password=True)
                .create(
                    {
                        "name": "Portal Official Smoke User",
                        "login": "portal.official.smoke@example.com",
                        "email": "portal.official.smoke@example.com",
                        "group_ids": [(6, 0, [portal_official_group.id])],
                    }
                )
            )
            referee = env["federation.referee"].create(
                {
                    "name": "Portal Official Smoke Referee",
                    "email": "portal.official.smoke@example.com",
                    "certification_level": "national",
                    "user_id": official_user.id,
                }
            )
            assignment_match = env["federation.match"].create(
                {
                    "tournament_id": officiating_tournament.id,
                    "home_team_id": home_team.id,
                    "away_team_id": away_team.id,
                    "date_scheduled": "2026-06-12 18:00:00",
                }
            )
            assignment = env["federation.match.referee"].create(
                {
                    "match_id": assignment_match.id,
                    "referee_id": referee.id,
                    "role": "head",
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
        cls.team_club = cls.env["federation.club"].browse(team_club.id)
        cls.team_user = cls.env["res.users"].browse(team_user.id)
        cls.season_club = cls.env["federation.club"].browse(season_club.id)
        cls.season_user = cls.env["res.users"].browse(season_user.id)
        cls.season_team = cls.env["federation.team"].browse(season_team.id)
        cls.open_season = cls.env["federation.season"].browse(open_season.id)
        cls.officiating_club = cls.env["federation.club"].browse(officiating_club.id)
        cls.home_team = cls.env["federation.team"].browse(home_team.id)
        cls.away_team = cls.env["federation.team"].browse(away_team.id)
        cls.officiating_season = cls.env["federation.season"].browse(
            officiating_season.id
        )
        cls.officiating_tournament = cls.env["federation.tournament"].browse(
            officiating_tournament.id
        )
        cls.official_user = cls.env["res.users"].browse(official_user.id)
        cls.referee = cls.env["federation.referee"].browse(referee.id)
        cls.assignment_match = cls.env["federation.match"].browse(assignment_match.id)
        cls.assignment = cls.env["federation.match.referee"].browse(assignment.id)

    def _create_roster_workspace_smoke_data(self):
        """Create committed data used by the split portal controller smoke test."""
        type(self)._roster_workspace_smoke_seq = (
            getattr(type(self), "_roster_workspace_smoke_seq", 0) + 1
        )
        suffix = type(self)._roster_workspace_smoke_seq

        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})

            roster_create_team = env["federation.team"].create(
                {
                    "name": "Portal Smoke Roster Opportunity",
                    "club_id": self.season_club.id,
                    "code": f"PSRO{suffix}",
                    "category": "senior",
                    "gender": "male",
                }
            )
            roster_create_registration = env["federation.season.registration"].create(
                {
                    "season_id": self.open_season.id,
                    "team_id": roster_create_team.id,
                    "user_id": self.season_user.id,
                }
            )
            roster_create_registration.action_confirm()

            workspace_team = env["federation.team"].create(
                {
                    "name": "Portal Smoke Workspace Team",
                    "club_id": self.season_club.id,
                    "code": f"PSWT{suffix}",
                    "category": "senior",
                    "gender": "male",
                }
            )
            workspace_registration = env["federation.season.registration"].create(
                {
                    "season_id": self.open_season.id,
                    "team_id": workspace_team.id,
                    "user_id": self.season_user.id,
                }
            )
            workspace_registration.action_confirm()

            live_tournament = env["federation.tournament"].create(
                {
                    "name": "Portal Smoke Workspace Tournament",
                    "code": f"PSWTN{suffix}",
                    "season_id": self.open_season.id,
                    "date_start": "2026-06-15",
                    "state": "in_progress",
                    "category": "senior",
                    "gender": "male",
                }
            )
            tournament_registration = env["federation.tournament.registration"].create(
                {
                    "tournament_id": live_tournament.id,
                    "team_id": workspace_team.id,
                    "user_id": self.season_user.id,
                }
            )
            tournament_registration.action_submit()
            tournament_registration.action_confirm()
            if tournament_registration.participant_id:
                tournament_registration.participant_id.action_confirm()

            player = env["federation.player"].create(
                {
                    "first_name": "Portal",
                    "last_name": "Smoke Roster",
                    "gender": "male",
                    "club_id": self.season_club.id,
                    "team_ids": [(4, workspace_team.id)],
                }
            )
            roster = env["federation.team.roster"].create(
                {
                    "name": "Portal Smoke Active Roster",
                    "team_id": workspace_team.id,
                    "season_id": self.open_season.id,
                    "season_registration_id": workspace_registration.id,
                }
            )
            roster_line = env["federation.team.roster.line"].create(
                {
                    "roster_id": roster.id,
                    "player_id": player.id,
                }
            )
            roster.action_activate()

            opponent_club = env["federation.club"].create(
                {
                    "name": "Portal Smoke Opponent Club",
                    "code": f"PSOC{suffix}",
                }
            )
            opponent_team = env["federation.team"].create(
                {
                    "name": "Portal Smoke Opponent Team",
                    "club_id": opponent_club.id,
                    "code": f"PSOT{suffix}",
                }
            )
            match = (
                env["federation.match"]
                .with_context(skip_auto_match_sheets=True)
                .create(
                    {
                        "tournament_id": live_tournament.id,
                        "home_team_id": workspace_team.id,
                        "away_team_id": opponent_team.id,
                        "date_scheduled": "2026-06-20 18:00:00",
                        "state": "scheduled",
                    }
                )
            )
            sheet = env["federation.match.sheet"].create(
                {
                    "name": "Portal Smoke Match Sheet",
                    "match_id": match.id,
                    "team_id": workspace_team.id,
                    "roster_id": roster.id,
                    "side": "home",
                }
            )
            env["federation.match.sheet.line"].create(
                {
                    "match_sheet_id": sheet.id,
                    "player_id": player.id,
                    "roster_line_id": roster_line.id,
                    "is_starter": True,
                }
            )
            foreign_player = env["federation.player"].create(
                {
                    "first_name": "Portal",
                    "last_name": "Smoke Foreign",
                    "gender": "male",
                    "club_id": opponent_club.id,
                    "team_ids": [(4, opponent_team.id)],
                }
            )
            foreign_roster = env["federation.team.roster"].create(
                {
                    "name": "Portal Smoke Foreign Roster",
                    "team_id": opponent_team.id,
                    "season_id": self.open_season.id,
                }
            )
            foreign_line = env["federation.team.roster.line"].create(
                {
                    "roster_id": foreign_roster.id,
                    "player_id": foreign_player.id,
                }
            )
            cr.commit()

        return {
            "create_registration_id": roster_create_registration.id,
            "workspace_team_id": workspace_team.id,
            "tournament_id": live_tournament.id,
            "sheet_id": sheet.id,
            "roster_id": roster.id,
            "roster_line_id": roster_line.id,
            "foreign_line_id": foreign_line.id,
        }

    def test_my_teams_empty_state_and_create_flow(self):
        self.authenticate(self.team_user.login, "ignored")

        list_response = self.url_open("/my/teams")
        self.assertEqual(list_response.status_code, 200)
        self.assertIn("Create Your First Team", list_response.text)

        form_response = self.url_open("/my/teams/new")
        create_response = self.url_open(
            "/my/teams/new",
            data={
                "csrf_token": _extract_csrf_token(form_response.text),
                "name": "Portal Team Smoke Squad",
                "club_id": str(self.team_club.id),
                "category": "senior",
                "gender": "male",
            },
            allow_redirects=True,
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertIn("Team created successfully", create_response.text)
        self.assertIn("Portal Team Smoke Squad", create_response.text)

    def test_my_players_empty_state_and_create_flow(self):
        self.authenticate(self.team_user.login, "ignored")

        list_response = self.url_open("/my/players")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.status_code, 200)
        self.assertNotIn("Internal Server Error", list_response.text)
        self.assertIn("Add Your First Player", list_response.text)

        form_response = self.url_open("/my/players/new")
        self.assertEqual(form_response.status_code, 200)
        self.assertNotIn("Internal Server Error", form_response.text)
        self.assertIn("Add Player", form_response.text)

        create_response = self.url_open(
            "/my/players/new",
            data={
                "csrf_token": _extract_csrf_token(form_response.text),
                "first_name": "Smoke",
                "last_name": "PlayerOne",
                "birth_date": "2000-03-20",
                "gender": "male",
                "email": "smoke.player@example.com",
            },
            allow_redirects=True,
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertIn("Player added successfully", create_response.text)
        self.assertIn("Smoke PlayerOne", create_response.text)
        self.assertNotIn("Internal Server Error", create_response.text)

    def test_my_players_list_renders_with_existing_players(self):
        """Player list renders correctly when players already exist in the club."""
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            env["federation.player"].create(
                {
                    "first_name": "Smoke",
                    "last_name": "ActivePlayer",
                    "club_id": self.team_club.id,
                    "state": "active",
                }
            )
            env["federation.player"].create(
                {
                    "first_name": "Smoke",
                    "last_name": "SuspendedPlayer",
                    "club_id": self.team_club.id,
                    "state": "suspended",
                }
            )
            cr.commit()

        self.authenticate(self.team_user.login, "ignored")

        list_response = self.url_open("/my/players")
        self.assertEqual(list_response.status_code, 200)
        self.assertNotIn("Internal Server Error", list_response.text)
        self.assertIn("Smoke ActivePlayer", list_response.text)
        self.assertIn("Smoke SuspendedPlayer", list_response.text)

        filter_response = self.url_open("/my/players?state=active")
        self.assertEqual(filter_response.status_code, 200)
        self.assertNotIn("Internal Server Error", filter_response.text)
        self.assertIn("Smoke ActivePlayer", filter_response.text)
        self.assertNotIn("Smoke SuspendedPlayer", filter_response.text)

    def test_season_registration_submit_flow_renders_success(self):
        self.authenticate(self.season_user.login, "ignored")

        list_response = self.url_open("/my/season-registrations")
        self.assertEqual(list_response.status_code, 200)
        self.assertIn(
            "No season registrations have been submitted yet.",
            list_response.text,
        )

        form_response = self.url_open("/my/season-registration/new")
        submit_response = self.url_open(
            "/my/season-registration/new",
            data={
                "csrf_token": _extract_csrf_token(form_response.text),
                "season_id": str(self.open_season.id),
                "team_id": str(self.season_team.id),
                "notes": "Ready for portal smoke coverage.",
            },
            allow_redirects=True,
        )

        self.assertEqual(submit_response.status_code, 200)
        self.assertIn("Season registration submitted", submit_response.text)
        self.assertIn(self.season_team.name, submit_response.text)
        self.assertNotIn("Internal Server Error", submit_response.text)

    def test_officiating_response_flow_renders_success(self):
        self.authenticate(self.official_user.login, "ignored")

        list_response = self.url_open("/my/referee-assignments")
        self.assertEqual(list_response.status_code, 200)
        self.assertIn("Next step:", list_response.text)
        self.assertIn("Respond now", list_response.text)

        detail_response = self.url_open(f"/my/referee-assignments/{self.assignment.id}")
        submit_response = self.url_open(
            f"/my/referee-assignments/{self.assignment.id}/respond",
            data={
                "csrf_token": _extract_csrf_token(detail_response.text),
                "action": "confirm",
                "response_note": "Confirmed from smoke test.",
            },
            allow_redirects=True,
        )

        self.assertEqual(submit_response.status_code, 200)
        self.assertIn("Assignment confirmed.", submit_response.text)
        self.assertIn("Confirmed from smoke test.", submit_response.text)

    def test_route_inventory_lists_smoke_covered_portal_routes(self):
        inventory_routes = {
            (entry["method"], entry["path"])
            for entry in load_route_inventory("sports_federation_portal")
        }

        self.assertEqual(
            inventory_routes,
            {
                ("GET", "/web/login"),
                ("GET", "/sports/tournament/<id>/operations"),
                ("POST", "/my/teams/new"),
                ("POST", "/my/players/new"),
                ("POST", "/my/season-registration/new"),
                ("POST", "/my/referee-assignments/<id>/respond"),
            },
        )

    def test_roster_workspace_and_match_day_routes_render_successfully(self):
        data = self._create_roster_workspace_smoke_data()

        self.authenticate(self.season_user.login, "ignored")

        roster_list_response = self.url_open("/my/rosters")
        self.assertEqual(roster_list_response.status_code, 200)
        self.assertIn("Portal Smoke Active Roster", roster_list_response.text)
        self.assertIn("Portal Smoke Roster Opportunity", roster_list_response.text)

        roster_create_response = self.url_open(
            f"/my/rosters/create/{data['create_registration_id']}",
            data={
                "csrf_token": _extract_csrf_token(roster_list_response.text),
            },
            allow_redirects=True,
        )
        self.assertEqual(roster_create_response.status_code, 200)
        self.assertIn(
            "Roster ready for editing in the portal.", roster_create_response.text
        )
        self.assertIn("Portal Smoke Roster Opportunity", roster_create_response.text)

        workspace_list_response = self.url_open("/my/tournament-workspaces")
        self.assertEqual(workspace_list_response.status_code, 200)
        self.assertIn("Portal Smoke Workspace Tournament", workspace_list_response.text)

        workspace_detail_response = self.url_open(
            f"/my/tournament-workspaces/{data['tournament_id']}/{data['workspace_team_id']}"
        )
        self.assertEqual(workspace_detail_response.status_code, 200)
        self.assertIn("Portal Smoke Workspace Team", workspace_detail_response.text)

        operations_response = self.url_open(
            f"/sports/tournament/{data['tournament_id']}/operations"
        )
        self.assertEqual(operations_response.status_code, 200)
        self.assertIn("Tournament Operations", operations_response.text)
        self.assertIn("sf_tournament_operations_root", operations_response.text)

        match_sheet_list_response = self.url_open("/my/match-sheets")
        self.assertEqual(match_sheet_list_response.status_code, 200)
        self.assertIn("Portal Smoke Match Sheet", match_sheet_list_response.text)

        match_sheet_detail_response = self.url_open(
            f"/my/match-sheets/{data['sheet_id']}"
        )
        match_sheet_prepare_response = self.url_open(
            f"/my/match-sheets/{data['sheet_id']}/prep",
            data={
                "csrf_token": _extract_csrf_token(match_sheet_detail_response.text),
                "coach_name": "Portal Smoke Coach",
                "manager_name": "Portal Smoke Manager",
                "notes": "Prepared through split controller smoke coverage.",
            },
            allow_redirects=True,
        )
        self.assertEqual(match_sheet_prepare_response.status_code, 200)
        self.assertIn("Match-day preparation saved.", match_sheet_prepare_response.text)

        match_day_response = self.url_open("/my/match-day")
        self.assertEqual(match_day_response.status_code, 200)
        self.assertIn(
            "Portal Smoke Workspace Team vs Portal Smoke Opponent Team",
            match_day_response.text,
        )
        self.assertIn("Open Sheet", match_day_response.text)

    def test_roster_routes_hide_foreign_rosters_and_lines(self):
        data = self._create_roster_workspace_smoke_data()

        self.authenticate(self.team_user.login, "ignored")

        foreign_roster_response = self.url_open(f"/my/rosters/{data['roster_id']}")
        # Cross-club access now returns 403 Access Denied (not a generic 404)
        self.assertEqual(foreign_roster_response.status_code, 403)

        self.authenticate(self.season_user.login, "ignored")

        foreign_line_response = self.url_open(
            f"/my/rosters/{data['roster_id']}/lines/{data['foreign_line_id']}/edit"
        )
        # Cross-club access now returns 403 Access Denied (not a generic 404)
        self.assertEqual(foreign_line_response.status_code, 403)

    def test_portal_error_hint_displayed_on_validation_error(self):
        """Contextual error_hint text appears in the page when a ValidationError occurs."""
        self._create_roster_workspace_smoke_data()
        self.authenticate(self.season_user.login, "ignored")

        # Hit the roster list page with an error_hint query param (simulating a
        # redirect from a failed POST) and verify the hint renders.
        hint_text = "Ensure the registration is confirmed and a roster has not already been created for this team."
        response = self.url_open(
            f"/my/rosters?error=Some+error&error_hint={hint_text.replace(' ', '+')}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(hint_text, response.text)
        # Raw Python exception noise must NOT appear.
        self.assertNotIn("Traceback", response.text)
