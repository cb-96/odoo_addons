import json

from odoo import http
from odoo.http import Response, request


class PublicCompetitionController(http.Controller):
    def _queries(self):
        return request.env["federation.public.competition.queries"]

    def _edition_or_404(self, slug):
        edition = self._queries().resolve_edition(slug)
        if not edition:
            raise request.not_found()
        return edition

    @http.route(
        ["/tournaments", "/tournaments/page/<int:page>"],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def legacy_tournament_hub(self, page=1, **kw):
        return request.redirect("/competitions", code=301)

    @http.route(
        ["/tournaments/<string:tournament_slug>", "/tournament/<int:tournament_id>"],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def legacy_tournament_detail(self, tournament_slug=None, tournament_id=None, **kw):
        division = self._queries().resolve_legacy_division(
            slug=tournament_slug, division_id=tournament_id
        )
        location = self._queries().canonical_location(division)
        if not location:
            raise request.not_found()
        return request.redirect(location, code=301)

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
