import json

from odoo import http
from odoo.http import Response, request

from ._public_request import PublicRequestInfrastructureMixin


class PublicCompetitionController(PublicRequestInfrastructureMixin, http.Controller):
    def _queries(self):
        return request.env["federation.public.competition.queries"]

    def _edition_or_404(self, slug):
        edition = self._queries().resolve_edition(slug)
        if not edition:
            raise request.not_found()
        return edition

    @http.route(
        ["/api/v1/competitions"],
        type="http",
        auth="public",
        methods=["GET"],
        website=False,
        sitemap=False,
    )
    def competition_api_index(self, **kw):
        blocked = self._rate_limit_response("public_competition_index")
        if blocked:
            return blocked
        editions = self._queries().list_editions(archived=False)
        payload = {
            "api_version": "v1",
            "contract": "competition_index",
            "competitions": [
                {
                    "id": e.id,
                    "name": e.name,
                    "slug": e.public_slug,
                    "state": e.state,
                    "season": e.season_id.display_name if e.season_id else None,
                    "website_url": f"/competitions/{e.public_slug}",
                    "api_url": e.get_public_api_path(),
                }
                for e in editions
            ],
        }
        return Response(
            json.dumps(payload, sort_keys=True),
            content_type="application/json; charset=utf-8",
            headers=[
                ("Cache-Control", "public, max-age=60"),
                ("X-Content-Type-Options", "nosniff"),
                ("X-Federation-Contract", "competition_index"),
                ("X-Federation-Contract-Version", "v1"),
            ],
        )

    @http.route(
        ["/api/v1/competitions/<string:edition_slug>"],
        type="http",
        auth="public",
        methods=["GET"],
        website=False,
        sitemap=False,
    )
    def competition_api_feed(self, edition_slug, **kw):
        blocked = self._rate_limit_response("public_competition_feed")
        if blocked:
            return blocked
        edition = self._edition_or_404(edition_slug)
        return Response(
            json.dumps(edition.get_public_api_payload(), sort_keys=True),
            content_type="application/json; charset=utf-8",
            headers=[
                ("Cache-Control", "public, max-age=60"),
                ("X-Content-Type-Options", "nosniff"),
                ("X-Federation-Contract", "competition_feed"),
                ("X-Federation-Contract-Version", "v1"),
            ],
        )

    @http.route(
        ["/competitions", "/competitions/page/<int:page>"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def competition_hub(self, page=1, search="", season_id=None, archive=False, **kw):
        editions = self._queries().list_editions(
            archived=bool(archive), search=search, season_id=season_id
        )
        return request.render(
            "sports_federation_public_site.public_competition_competition_hub",
            {
                "editions": editions,
                "search": search,
                "archive": bool(archive),
                "seasons": request.env["federation.season"]
                .sudo()
                .search([("active", "=", True)], order="date_start desc,id desc"),
            },
        )

    @http.route(
        ["/competitions/archive"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def competition_archive(self, **kw):
        return self.competition_hub(archive=True, **kw)

    @http.route(
        ["/competitions/<string:edition_slug>"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def competition_detail(self, edition_slug, division_id=None, **kw):
        edition = self._edition_or_404(edition_slug)
        summary = self._queries().edition_summary(edition)
        division = self._queries().resolve_division(edition, division_id)
        if division_id and not division:
            raise request.not_found()
        summary.update(
            {
                "division": division,
                "stage_cards": request.env[
                    "federation.public.format.queries"
                ].stage_cards(edition, division),
            }
        )
        return request.render(
            "sports_federation_public_site.public_competition_competition_detail",
            summary,
        )

    @http.route(
        ["/competitions/<string:edition_slug>/format"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def competition_format(self, edition_slug, division_id=None, **kw):
        edition = self._edition_or_404(edition_slug)
        divisions = self._queries().public_divisions(edition)
        division = self._queries().resolve_division(edition, division_id)
        if division_id and not division:
            raise request.not_found()
        return request.render(
            "sports_federation_public_site.public_competition_competition_format",
            {
                "edition": edition,
                "divisions": divisions,
                "division": division,
                "stage_cards": request.env[
                    "federation.public.format.queries"
                ].stage_cards(edition, division),
                "page_name": "format",
            },
        )

    @http.route(
        ["/competitions/<string:edition_slug>/schedule"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def competition_schedule(self, edition_slug, **kw):
        edition = self._edition_or_404(edition_slug)
        matchdays = request.env["federation.public.schedule.queries"].edition_matchdays(
            edition
        )
        return request.render(
            "sports_federation_public_site.public_competition_competition_schedule",
            {"edition": edition, "matchdays": matchdays, "page_name": "schedule"},
        )

    @http.route(
        ["/competitions/<string:edition_slug>/gamedays/<int:matchday_id>"],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def competition_gameday(
        self,
        edition_slug,
        matchday_id,
        team_id=None,
        court_id=None,
        display=False,
        **kw,
    ):
        edition = self._edition_or_404(edition_slug)
        matchday = (
            request.env["federation.matchday"]
            .sudo()
            .search(
                [
                    ("id", "=", matchday_id),
                    ("edition_id", "=", edition.id),
                    ("current_publication_id.state", "=", "live"),
                ],
                limit=1,
            )
        )
        if not matchday:
            raise request.not_found()
        board = request.env["federation.public.schedule.queries"].matchday_board(
            matchday, team_id=team_id, court_id=court_id
        )
        board.update(
            {
                "edition": edition,
                "matchday": matchday,
                "team_id": int(team_id) if team_id else False,
                "court_id": int(court_id) if court_id else False,
                "display": bool(display),
            }
        )
        return request.render(
            (
                "sports_federation_public_site.public_competition_gameday_display"
                if display
                else "sports_federation_public_site.public_competition_gameday"
            ),
            board,
        )

    @http.route(
        ["/competitions/<string:edition_slug>/gamedays/<int:matchday_id>/status.json"],
        type="http",
        auth="public",
        website=False,
        sitemap=False,
    )
    def competition_gameday_status(self, edition_slug, matchday_id, **kw):
        edition = self._edition_or_404(edition_slug)
        matchday = (
            request.env["federation.matchday"]
            .sudo()
            .search(
                [
                    ("id", "=", matchday_id),
                    ("edition_id", "=", edition.id),
                    ("current_publication_id.state", "=", "live"),
                ],
                limit=1,
            )
        )
        if not matchday:
            raise request.not_found()
        board = request.env["federation.public.schedule.queries"].matchday_board(
            matchday
        )
        payload = {
            "publication": board["publication"].version,
            "matches": [
                {
                    "id": row["match"].id,
                    "status": row["status"],
                    "home_score": row["match"].home_score,
                    "away_score": row["match"].away_score,
                    "result_state": row["match"].result_state,
                    "court": row["slot"].court_id.display_name if row["slot"] else None,
                    "start": (
                        row["slot"].start_datetime.isoformat() if row["slot"] else None
                    ),
                }
                for row in board["matches"]
            ],
        }
        body = json.dumps(payload, sort_keys=True)
        return Response(
            body,
            content_type="application/json; charset=utf-8",
            headers=[("Cache-Control", "public, max-age=20")],
        )
