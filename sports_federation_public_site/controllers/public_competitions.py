from odoo import http
from odoo.addons.sports_federation_base.request_security import (
    FederationRequestSecurityMixin,
)
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, ValidationError
from odoo.http import Response, request
from ._filters import TournamentHubFilterMixin
from ._public_request import PublicRequestInfrastructureMixin


class PublicTournamentHubController(
    PublicRequestInfrastructureMixin,
    FederationRequestSecurityMixin,
    TournamentHubFilterMixin,
    http.Controller,
):

    @http.route(
        ["/competitions/api/json"],
        type="jsonrpc",
        auth="public",
        methods=["POST"],
    )
    def competitions_api_json(self, **kw):
        """Handle competitions API JSON."""
        blocked_response = self._rate_limit_response("public_competitions_json")
        if blocked_response:
            return blocked_response
        tournaments = request.env[
            "federation.tournament"
        ].get_public_published_tournaments(limit=None)
        return {
            "tournaments": [
                {
                    "id": tournament.id,
                    "name": tournament.name,
                    "slug": tournament.get_public_slug_value(),
                    "state": tournament.state,
                    "date_start": (
                        tournament.date_start.isoformat()
                        if tournament.date_start
                        else None
                    ),
                    "date_end": (
                        tournament.date_end.isoformat() if tournament.date_end else None
                    ),
                    "url": tournament.get_public_path(),
                    "featured": tournament.public_featured,
                }
                for tournament in tournaments
            ]
        }

    def _legacy_tournaments_list(self, page=1, search="", **kw):
        """Handle tournaments list."""
        filters = self._build_filters(search=search, **kw)
        Tournament = request.env["federation.tournament"].sudo()

        main_domain = self._build_main_tournament_domain(filters)
        total = Tournament.search_count(main_domain)
        step = 12
        pager = portal_pager(
            url="/competitions",
            total=total,
            page=page,
            step=step,
            url_args={key: value for key, value in filters.items() if value},
        )
        tournaments = Tournament.search(
            main_domain,
            limit=step,
            offset=pager["offset"],
            order="date_start desc, id desc",
        )

        shared_public_domain = self._build_shared_filter_domain(filters)
        featured_public_domain = list(shared_public_domain)
        if filters["state"]:
            featured_public_domain.append(("state", "=", filters["state"]))

        if filters["state"] and filters["state"] not in ("", "closed", "cancelled"):
            archived_public_tournaments = Tournament.browse([])
        else:
            archive_domain = list(shared_public_domain)
            if filters["state"] in ("closed", "cancelled"):
                archive_domain.append(("state", "=", filters["state"]))
            archived_public_tournaments = Tournament.get_public_archived_tournaments(
                limit=6, extra_domain=archive_domain
            )

        live_public_tournaments = (
            Tournament.get_public_live_tournaments(
                limit=4, extra_domain=shared_public_domain
            )
            if filters["state"] in ("", "in_progress")
            else Tournament.browse([])
        )
        recent_public_tournaments = (
            Tournament.get_public_recent_result_tournaments(
                limit=4, extra_domain=shared_public_domain
            )
            if filters["state"] != "cancelled"
            else Tournament.browse([])
        )
        featured_public_tournaments = Tournament.get_public_featured_tournaments(
            limit=6, extra_domain=featured_public_domain
        )

        all_public_tournaments = (
            tournaments
            | featured_public_tournaments
            | archived_public_tournaments
            | live_public_tournaments
            | recent_public_tournaments
        )
        tournament_public_flags = {
            tournament.id: {
                "has_schedule": bool(tournament.get_public_schedule_sections()),
                "has_bracket": bool(tournament.get_public_bracket_sections()),
            }
            for tournament in all_public_tournaments
        }

        values = {
            "tournaments": tournaments,
            "pager": pager,
            "filters": filters,
            "featured_public_tournaments": featured_public_tournaments,
            "archived_public_tournaments": archived_public_tournaments,
            "live_public_tournaments": live_public_tournaments,
            "recent_public_tournaments": recent_public_tournaments,
            "tournament_public_flags": tournament_public_flags,
            "page_name": "tournaments_hub",
        }
        values.update(self._get_filter_reference_data())
        return request.render(
            "sports_federation_public_site.page_tournaments_hub", values
        )

    def _legacy_tournament_detail(self, tournament_slug=None, tournament_id=None, **kw):
        """Handle tournament detail."""
        tournament = self._resolve_tournament(
            tournament_slug=tournament_slug,
            tournament_id=tournament_id,
            public_access="detail",
        )
        if not tournament.exists():
            self._raise_not_found()

        if tournament_slug:
            redirect = self._canonical_redirect(
                tournament, tournament_slug, tournament.get_public_path
            )
            if redirect:
                return redirect
        else:
            return request.redirect(tournament.get_public_path())

        return request.render(
            "sports_federation_public_site.page_tournament_overview",
            tournament.get_public_detail_context(),
        )

    def _competition_division_or_404(
        self, edition_slug, division_slug=None, division_id=None
    ):
        queries = request.env["federation.public.competition.queries"]
        edition = queries.resolve_edition(edition_slug)
        if not edition:
            self._raise_not_found()
        divisions = queries.public_divisions(edition)
        if division_id:
            try:
                division_id = int(division_id)
            except (TypeError, ValueError):
                self._raise_not_found()
            division = divisions.filtered(lambda item: item.id == division_id)[:1]
        else:
            division = divisions.filtered(
                lambda item: item.get_public_slug_value() == division_slug
            )[:1]
        if not division:
            self._raise_not_found()
        return edition, division

    @http.route(
        ["/competitions/<string:edition_slug>/register"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def competition_register_form(self, edition_slug, division_id=None, **kw):
        edition, division = self._competition_division_or_404(
            edition_slug, division_id=division_id
        )
        if division.state != "open":
            return request.redirect(f"/competitions/{edition.public_slug}")
        clubs = self._get_request_user_clubs()
        if not clubs:
            return request.render(
                "sports_federation_public_site.page_tournament_register",
                {
                    "error": "You are not registered as a club representative. Please contact the federation.",
                    "tournament": division,
                },
            )
        Entry = request.env["federation.competition.entry"]
        window = Entry._portal_open_window_for_division(division)
        if not window:
            return request.redirect(f"/competitions/{edition.public_slug}")
        existing = Entry.sudo().search(
            [
                ("window_id", "=", window.id),
                ("team_id.club_id", "in", clubs.ids),
                ("state", "!=", "withdrawn"),
            ]
        )
        blocked = {
            team.id: "Already registered or currently awaiting review."
            for team in existing.mapped("team_id")
        }
        snapshot = division.sudo().get_team_selection_snapshot(
            extra_domain=[("club_id", "in", clubs.ids)],
            blocked_reason_by_team_id=blocked,
        )
        return request.render(
            "sports_federation_public_site.page_tournament_register",
            {
                "tournament": division,
                "clubs": clubs,
                "teams": snapshot["available_teams"],
                "excluded_teams": [
                    {
                        "name": item["team"].name,
                        "club": item["team"].club_id.name,
                        "reason": item["reason"],
                    }
                    for item in snapshot["excluded_teams"]
                ],
                "error": kw.get("error"),
                "success": kw.get("success"),
            },
        )

    @http.route(
        ["/competitions/<string:edition_slug>/register"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=False,
    )
    def competition_register_submit(
        self, edition_slug, division_id=None, team_id=None, notes="", **kw
    ):
        edition, division = self._competition_division_or_404(
            edition_slug, division_id=division_id
        )
        path = division.get_public_register_path()
        if division.state != "open":
            return request.redirect(f"/competitions/{edition.public_slug}")
        try:
            self._validate_manual_csrf(kw.get("csrf_token"))
            team_id = int(team_id)
            request.env["federation.competition.entry"]._portal_submit_entry(
                division,
                request.env["federation.team"].sudo().browse(team_id),
                notes=notes,
                user=request.env.user,
            )
        except (AccessError, ValidationError, TypeError, ValueError) as error:
            return self._redirect_with_error(path, str(error))
        return request.redirect(f"{path}&success=Registration+submitted+successfully")

    @http.route(
        [
            "/competitions/<string:edition_slug>/divisions/<string:division_slug>/schedule.ics"
        ],
        type="http",
        auth="public",
        methods=["GET"],
    )
    def competition_division_schedule_ics(self, edition_slug, division_slug, **kw):
        _edition, division = self._competition_division_or_404(
            edition_slug, division_slug=division_slug
        )
        content = division.get_public_schedule_ics()
        filename = f"{division.get_public_slug_value()}-schedule.ics"
        return Response(
            content,
            content_type="text/calendar; charset=utf-8",
            headers=[
                ("Content-Disposition", f'attachment; filename="{filename}"'),
                ("X-Federation-Contract", "competition_division_schedule_ics"),
                ("X-Federation-Contract-Version", "ics_v1"),
            ],
        )

    @http.route(["/teams/<string:team_slug>"], type="http", auth="public", website=True)
    def team_detail(self, team_slug, **kw):
        """Handle team detail."""
        team = self._resolve_team(team_slug, public_access="profile")
        if not team.exists() or not team.can_access_public_profile():
            self._raise_not_found()

        redirect = self._canonical_redirect(team, team_slug, team.get_public_path)
        if redirect:
            return redirect

        values = {
            "team": team,
            "public_tournaments": team.get_public_tournaments(limit=8),
            "upcoming_matches": team.get_public_upcoming_matches(limit=4),
            "recent_results": team.get_public_recent_result_matches(limit=4),
            "standing_lines": team.get_public_standing_lines(limit=8),
            "page_name": "public_team_profile",
        }
        return request.render(
            "sports_federation_public_site.page_public_team_profile", values
        )
