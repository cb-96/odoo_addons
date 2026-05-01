import json

from odoo import http
from odoo.http import Response, request

from .public_competitions import PublicTournamentHubController


class PublicSeasonAndTeamController(PublicTournamentHubController):
    def _resolve_season(self, season_slug=None, season_id=None, public_access=None):
        """Resolve season."""
        Season = request.env["federation.season"]
        public_domain = self._build_season_public_domain(public_access)
        if season_id:
            return Season.sudo().search(
                [("id", "=", int(season_id))] + public_domain,
                limit=1,
            )
        if season_slug:
            return Season.resolve_public_slug(
                season_slug,
                extra_domain=public_domain,
            )
        return Season.browse([])

    @http.route(["/seasons"], type="http", auth="public", website=True)
    def seasons_list(self, **kw):
        """Handle seasons list."""
        seasons = request.env["federation.season"].get_public_published_seasons()
        values = {
            "seasons": seasons,
            "page_name": "public_seasons",
        }
        return request.render(
            "sports_federation_public_site.page_public_seasons", values
        )

    @http.route(
        ["/seasons/<string:season_slug>", "/season/<int:season_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def season_detail(self, season_slug=None, season_id=None, **kw):
        """Handle season detail."""
        season = self._resolve_season(
            season_slug=season_slug,
            season_id=season_id,
            public_access="detail",
        )
        if not season.exists() or not season.can_access_public_detail():
            self._raise_not_found()
        if season_slug:
            redirect = self._canonical_redirect(
                season, season_slug, season.get_public_path
            )
            if redirect:
                return redirect
        else:
            return request.redirect(season.get_public_path())

        Tournament = request.env["federation.tournament"]
        values = {
            "season": season,
            "featured_tournaments": Tournament.get_public_featured_tournaments(
                extra_domain=[("season_id", "=", season.id)]
            ),
            "recent_tournaments": season.get_public_recent_tournaments(limit=6),
            "editorial_items": season.get_public_editorial_items(limit=8),
            "page_name": "public_season_detail",
        }
        return request.render(
            "sports_federation_public_site.page_public_season_detail", values
        )

    @http.route(
        ["/teams/<string:team_slug>/schedule"], type="http", auth="public", website=True
    )
    def team_schedule(self, team_slug, **kw):
        """Handle team schedule."""
        team = self._resolve_team(team_slug, public_access="profile")
        if not team.exists() or not team.can_access_public_profile():
            self._raise_not_found()

        redirect = self._canonical_redirect(
            team, team_slug, team.get_public_schedule_path
        )
        if redirect:
            return redirect

        values = {
            "team": team,
            "schedule_sections": team.get_public_schedule_sections(),
            "page_name": "public_team_schedule",
        }
        return request.render(
            "sports_federation_public_site.page_public_team_schedule", values
        )

    @http.route(
        ["/teams/<string:team_slug>/results"], type="http", auth="public", website=True
    )
    def team_results(self, team_slug, **kw):
        """Handle team results."""
        team = self._resolve_team(team_slug, public_access="profile")
        if not team.exists() or not team.can_access_public_profile():
            self._raise_not_found()

        redirect = self._canonical_redirect(
            team, team_slug, team.get_public_results_path
        )
        if redirect:
            return redirect

        values = {
            "team": team,
            "result_sections": team.get_public_result_sections(),
            "page_name": "public_team_results",
        }
        return request.render(
            "sports_federation_public_site.page_public_team_results", values
        )

    @http.route(
        ["/teams/<string:team_slug>/schedule.ics"],
        type="http",
        auth="public",
        methods=["GET"],
    )
    def team_schedule_ics(self, team_slug, **kw):
        """Handle team schedule ICS."""
        team = self._resolve_team(team_slug, public_access="profile")
        if not team.exists() or not team.can_access_public_profile():
            self._raise_not_found()

        redirect = self._canonical_redirect(
            team, team_slug, team.get_public_schedule_ics_path
        )
        if redirect:
            return redirect

        filename = f"{team.get_public_slug_value()}-schedule.ics"
        return Response(
            team.get_public_schedule_ics(),
            content_type="text/calendar; charset=utf-8",
            headers=[
                ("Content-Disposition", f'attachment; filename="{filename}"'),
                ("X-Federation-Contract", "team_schedule_ics"),
                ("X-Federation-Contract-Version", "ics_v1"),
            ],
        )

    @http.route(
        ["/api/v1/teams/<string:team_slug>/feed"],
        type="http",
        auth="public",
        methods=["GET"],
    )
    def team_feed_v1(self, team_slug, **kw):
        """Handle team feed v1."""
        blocked_response = self._rate_limit_response("public_team_feed")
        if blocked_response:
            return blocked_response
        team = self._resolve_team(team_slug, public_access="profile")
        if not team.exists() or not team.can_access_public_profile():
            self._raise_not_found()

        return Response(
            json.dumps(team.get_public_feed_payload()),
            content_type="application/json; charset=utf-8",
            headers=[
                ("X-Federation-Contract", "team_feed"),
                ("X-Federation-Contract-Version", "v1"),
            ],
        )
