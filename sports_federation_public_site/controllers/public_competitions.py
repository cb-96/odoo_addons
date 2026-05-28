import json
from urllib.parse import quote_plus

from odoo import http
from odoo.addons.sports_federation_base.request_security import (
    FederationRequestSecurityMixin,
)
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, ValidationError
from odoo.http import Response, request

from ._filters import TournamentHubFilterMixin


class PublicTournamentHubController(
    FederationRequestSecurityMixin,
    TournamentHubFilterMixin,
    http.Controller,
):

    def _raise_not_found(self):
        """Raise the framework 404 exception for hidden public resources."""
        raise request.not_found()

    def _make_json_response(self, payload, status=200, headers=None):
        """Build a JSON response for public API callers."""
        make_json_response = getattr(request, "make_json_response", None)
        if make_json_response:
            return make_json_response(payload, status=status, headers=headers)
        return Response(
            json.dumps(payload),
            status=status,
            headers=headers or [],
            content_type="application/json; charset=utf-8",
        )

    def _resolve_tournament(
        self,
        tournament_slug=None,
        tournament_id=None,
        tournament=False,
        public_access=None,
    ):
        """Resolve tournament."""
        Tournament = request.env["federation.tournament"]
        public_domain = self._build_tournament_public_domain(public_access)
        if tournament:
            return Tournament.sudo().search(
                [("id", "=", tournament.id)] + public_domain,
                limit=1,
            )
        if tournament_id:
            return Tournament.sudo().search(
                [("id", "=", int(tournament_id))] + public_domain,
                limit=1,
            )
        if tournament_slug:
            return Tournament.resolve_public_slug(
                tournament_slug,
                extra_domain=public_domain,
            )
        return Tournament.browse([])

    def _resolve_team(self, team_slug, public_access=None):
        """Resolve team."""
        return request.env["federation.team"].resolve_public_slug(
            team_slug,
            extra_domain=self._build_team_public_domain(public_access),
        )

    def _canonical_redirect(self, record, slug_value, path_getter):
        """Handle canonical redirect."""
        if slug_value != record.get_public_slug_value():
            return request.redirect(path_getter())
        return None

    def _get_request_user_clubs(self):
        """Return club scope for the authenticated website user.

        Returns an empty recordset when sports_federation_portal is not
        installed (no ``federation.club.representative`` model available).
        """
        ClubRep = request.env.get("federation.club.representative")
        if ClubRep is None:
            return request.env["federation.club"].browse([])
        return ClubRep.sudo()._get_clubs_for_user(user=request.env.user)

    def _redirect_with_error(self, path, message):
        """Redirect to a path with a user-facing error message."""
        return request.redirect(f"{path}?error={quote_plus(message)}")

    def _get_rate_limit_subject(self):
        """Return the caller fingerprint for public endpoints."""
        headers = getattr(request.httprequest, "headers", {}) or {}
        forwarded_for = (headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
        remote_addr = (
            forwarded_for
            or (getattr(request.httprequest, "remote_addr", "") or "").strip()
        )
        return f"ip:{remote_addr or 'unknown'}"

    def _rate_limit_response(self, scope):
        """Return a 429 response when the caller exceeds the route limit."""
        decision = (
            request.env["federation.request.rate.limit"]
            .sudo()
            .consume(
                scope,
                self._get_rate_limit_subject(),
            )
        )
        if decision["allowed"]:
            return False
        return self._make_json_response(
            {
                "error": (
                    "Too many requests. "
                    f"Retry after {decision['retry_after']} seconds."
                ),
                "error_code": "retryable_delivery",
            },
            status=429,
            headers=[("Retry-After", str(decision["retry_after"]))],
        )

    @http.route(["/competitions"], type="http", auth="public", website=True)
    def competitions_list(self, **kw):
        """Handle competitions list."""
        return request.redirect("/tournaments#published")

    @http.route(["/competitions/archive"], type="http", auth="public", website=True)
    def competitions_archive(self, **kw):
        """Handle competitions archive."""
        return request.redirect("/tournaments?state=closed#published-archive")

    @http.route(
        ["/competitions/api/json", "/tournaments/api/json"],
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

    @http.route(
        ["/tournaments", "/tournaments/page/<int:page>"],
        type="http",
        auth="public",
        website=True,
    )
    def tournaments_list(self, page=1, search="", **kw):
        """Handle tournaments list."""
        filters = self._build_filters(search=search, **kw)
        Tournament = request.env["federation.tournament"].sudo()

        main_domain = self._build_main_tournament_domain(filters)
        total = Tournament.search_count(main_domain)
        step = 12
        pager = portal_pager(
            url="/tournaments",
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

    @http.route(
        [
            "/tournament/<int:tournament_id>/coverage",
            "/competitions/<model('federation.tournament'):tournament>",
        ],
        type="http",
        auth="public",
        website=True,
    )
    def legacy_public_overview(self, tournament_id=None, tournament=False, **kw):
        """Handle legacy public overview."""
        tournament = self._resolve_tournament(
            tournament_id=tournament_id,
            tournament=tournament,
            public_access="detail",
        )
        if not tournament.exists():
            self._raise_not_found()
        return request.redirect(tournament.get_public_path())

    @http.route(
        ["/tournaments/<string:tournament_slug>", "/tournament/<int:tournament_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def tournament_detail(self, tournament_slug=None, tournament_id=None, **kw):
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

    @http.route(
        ["/tournaments/<string:tournament_slug>/register"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def tournament_register_form(self, tournament_slug=None, **kw):
        """Handle tournament register form."""
        tournament = self._resolve_tournament(
            tournament_slug=tournament_slug,
            public_access="detail",
        )
        if not tournament.exists() or tournament.state != "open":
            return request.redirect("/tournaments")

        clubs = self._get_request_user_clubs()
        if not clubs:
            values = {
                "error": "You are not registered as a club representative. Please contact the federation.",
                "tournament": tournament,
            }
            return request.render(
                "sports_federation_public_site.page_tournament_register", values
            )

        existing = (
            request.env["federation.tournament.registration"]
            .sudo()
            .search(
                [
                    ("tournament_id", "=", tournament.id),
                    ("team_id.club_id", "in", clubs.ids),
                    ("state", "!=", "cancelled"),
                ]
            )
        )
        blocked_reason_by_team_id = {
            team.id: "Already registered or currently awaiting review."
            for team in existing.mapped("team_id")
        }
        selection_snapshot = tournament.sudo().get_team_selection_snapshot(
            extra_domain=[("club_id", "in", clubs.ids)],
            blocked_reason_by_team_id=blocked_reason_by_team_id,
        )
        values = {
            "tournament": tournament,
            "clubs": clubs,
            "teams": selection_snapshot["available_teams"],
            "excluded_teams": [
                {
                    "name": item["team"].name,
                    "club": item["team"].club_id.name,
                    "reason": item["reason"],
                }
                for item in selection_snapshot["excluded_teams"]
            ],
            "error": kw.get("error"),
            "success": kw.get("success"),
        }
        return request.render(
            "sports_federation_public_site.page_tournament_register", values
        )

    @http.route(
        ["/tournament/<int:tournament_id>/register"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def tournament_register_form_legacy(self, tournament_id, **kw):
        """Handle tournament register form legacy."""
        tournament = self._resolve_tournament(
            tournament_id=tournament_id,
            public_access="detail",
        )
        if not tournament.exists():
            return request.redirect("/tournaments")
        return request.redirect(tournament.get_public_register_path())

    @http.route(
        ["/tournaments/<string:tournament_slug>/register"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=False,
    )
    def tournament_register_submit(self, tournament_slug, team_id, notes="", **kw):
        """Handle tournament register submit."""
        tournament = self._resolve_tournament(
            tournament_slug=tournament_slug,
            public_access="detail",
        )
        if not tournament.exists() or tournament.state != "open":
            return request.redirect("/tournaments")

        try:
            self._validate_manual_csrf(kw.get("csrf_token"))
        except ValidationError as error:
            return self._redirect_with_error(
                tournament.get_public_register_path(),
                str(error),
            )

        try:
            team_id = int(team_id)
        except (ValueError, TypeError):
            return self._redirect_with_error(
                tournament.get_public_register_path(),
                "Invalid team selection",
            )

        Registration = request.env["federation.tournament.registration"]
        if not hasattr(Registration, "_portal_submit_registration_request"):
            return self._redirect_with_error(
                tournament.get_public_register_path(),
                "Online registration is not available at this time.",
            )

        try:
            Registration._portal_submit_registration_request(
                tournament,
                request.env["federation.team"].sudo().browse(team_id),
                notes=notes,
                user=request.env.user,
            )
        except (AccessError, ValidationError) as error:
            return self._redirect_with_error(
                tournament.get_public_register_path(),
                str(error),
            )

        return request.redirect(
            f"{tournament.get_public_register_path()}?success=Registration+submitted+successfully"
        )

    @http.route(
        ["/tournament/<int:tournament_id>/register"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=False,
    )
    def tournament_register_submit_legacy(self, tournament_id, team_id, notes="", **kw):
        """Handle tournament register submit legacy."""
        tournament = self._resolve_tournament(
            tournament_id=tournament_id,
            public_access="detail",
        )
        if not tournament.exists():
            return request.redirect("/tournaments")
        return self.tournament_register_submit(
            tournament.get_public_slug_value(), team_id, notes=notes, **kw
        )

    @http.route(
        [
            "/tournaments/<string:tournament_slug>/teams",
            "/tournament/<int:tournament_id>/teams",
            "/competitions/<model('federation.tournament'):tournament>/teams",
        ],
        type="http",
        auth="public",
        website=True,
    )
    def tournament_teams(
        self, tournament_slug=None, tournament_id=None, tournament=False, **kw
    ):
        """Handle tournament teams."""
        tournament = self._resolve_tournament(
            tournament_slug=tournament_slug,
            tournament_id=tournament_id,
            tournament=tournament,
            public_access="detail",
        )
        if not tournament.exists():
            self._raise_not_found()
        if tournament_slug:
            redirect = self._canonical_redirect(
                tournament, tournament_slug, tournament.get_public_teams_path
            )
            if redirect:
                return redirect
        else:
            return request.redirect(tournament.get_public_teams_path())

        values = {
            "tournament": tournament,
            "participants": tournament.get_public_participants(),
            "page_name": "competition_teams",
        }
        return request.render(
            "sports_federation_public_site.page_competition_teams", values
        )

    @http.route(
        [
            "/tournaments/<string:tournament_slug>/standings",
            "/tournament/<int:tournament_id>/standings",
            "/competitions/<model('federation.tournament'):tournament>/standings",
        ],
        type="http",
        auth="public",
        website=True,
    )
    def tournament_standings(
        self, tournament_slug=None, tournament_id=None, tournament=False, **kw
    ):
        """Handle tournament standings."""
        tournament = self._resolve_tournament(
            tournament_slug=tournament_slug,
            tournament_id=tournament_id,
            tournament=tournament,
            public_access="standings",
        )
        if not tournament.exists():
            self._raise_not_found()
        if tournament_slug:
            redirect = self._canonical_redirect(
                tournament, tournament_slug, tournament.get_public_standings_path
            )
            if redirect:
                return redirect
        else:
            return request.redirect(tournament.get_public_standings_path())

        values = {
            "tournament": tournament,
            "standings": tournament.get_public_standings(),
            "page_name": "competition_standings",
        }
        return request.render(
            "sports_federation_public_site.page_competition_standings", values
        )

    @http.route(
        [
            "/tournaments/<string:tournament_slug>/results",
            "/tournament/<int:tournament_id>/results",
            "/competitions/<model('federation.tournament'):tournament>/results",
        ],
        type="http",
        auth="public",
        website=True,
    )
    def tournament_results(
        self, tournament_slug=None, tournament_id=None, tournament=False, **kw
    ):
        """Handle tournament results."""
        tournament = self._resolve_tournament(
            tournament_slug=tournament_slug,
            tournament_id=tournament_id,
            tournament=tournament,
            public_access="results",
        )
        if not tournament.exists():
            self._raise_not_found()
        if tournament_slug:
            redirect = self._canonical_redirect(
                tournament, tournament_slug, tournament.get_public_results_path
            )
            if redirect:
                return redirect
        else:
            return request.redirect(tournament.get_public_results_path())

        values = {
            "tournament": tournament,
            "matches": tournament.get_public_result_matches(),
            "page_name": "competition_results",
        }
        return request.render(
            "sports_federation_public_site.page_competition_results", values
        )

    @http.route(
        [
            "/tournaments/<string:tournament_slug>/schedule",
            "/tournament/<int:tournament_id>/schedule",
            "/competitions/<model('federation.tournament'):tournament>/schedule",
        ],
        type="http",
        auth="public",
        website=True,
    )
    def tournament_schedule(
        self, tournament_slug=None, tournament_id=None, tournament=False, **kw
    ):
        """Handle tournament schedule."""
        tournament = self._resolve_tournament(
            tournament_slug=tournament_slug,
            tournament_id=tournament_id,
            tournament=tournament,
            public_access="detail",
        )
        if not tournament.exists():
            self._raise_not_found()
        if tournament_slug:
            redirect = self._canonical_redirect(
                tournament, tournament_slug, tournament.get_public_schedule_path
            )
            if redirect:
                return redirect
        else:
            return request.redirect(tournament.get_public_schedule_path())

        values = {
            "tournament": tournament,
            "schedule_sections": tournament.get_public_schedule_sections(),
            "page_name": "competition_schedule",
        }
        return request.render(
            "sports_federation_public_site.page_competition_schedule", values
        )

    @http.route(
        [
            "/tournaments/<string:tournament_slug>/bracket",
            "/tournament/<int:tournament_id>/bracket",
            "/competitions/<model('federation.tournament'):tournament>/bracket",
        ],
        type="http",
        auth="public",
        website=True,
    )
    def tournament_bracket(
        self, tournament_slug=None, tournament_id=None, tournament=False, **kw
    ):
        """Handle tournament bracket."""
        tournament = self._resolve_tournament(
            tournament_slug=tournament_slug,
            tournament_id=tournament_id,
            tournament=tournament,
            public_access="detail",
        )
        if not tournament.exists() or not tournament.has_public_bracket():
            self._raise_not_found()
        if tournament_slug:
            redirect = self._canonical_redirect(
                tournament, tournament_slug, tournament.get_public_bracket_path
            )
            if redirect:
                return redirect
        else:
            return request.redirect(tournament.get_public_bracket_path())

        values = {
            "tournament": tournament,
            "bracket_sections": tournament.get_public_bracket_sections(),
            "page_name": "competition_bracket",
        }
        return request.render(
            "sports_federation_public_site.page_competition_bracket", values
        )

    @http.route(
        [
            "/tournaments/<string:tournament_slug>/schedule.ics",
            "/tournament/<int:tournament_id>/schedule.ics",
        ],
        type="http",
        auth="public",
        methods=["GET"],
    )
    def tournament_schedule_ics(self, tournament_slug=None, tournament_id=None, **kw):
        """Handle tournament schedule ICS."""
        tournament = self._resolve_tournament(
            tournament_slug=tournament_slug,
            tournament_id=tournament_id,
            public_access="detail",
        )
        if not tournament.exists():
            self._raise_not_found()
        if tournament_slug:
            redirect = self._canonical_redirect(
                tournament, tournament_slug, tournament.get_public_schedule_ics_path
            )
            if redirect:
                return redirect
        content = tournament.get_public_schedule_ics()
        filename = f"{tournament.get_public_slug_value()}-schedule.ics"
        return Response(
            content,
            content_type="text/calendar; charset=utf-8",
            headers=[
                ("Content-Disposition", f'attachment; filename="{filename}"'),
                ("X-Federation-Contract", "tournament_schedule_ics"),
                ("X-Federation-Contract-Version", "ics_v1"),
            ],
        )

    @http.route(
        [
            "/api/v1/tournaments/<string:tournament_slug>/feed",
            "/api/v1/tournaments/<int:tournament_id>/feed",
            "/api/v1/competitions/<int:tournament_id>/feed",
        ],
        type="http",
        auth="public",
        methods=["GET"],
    )
    def competition_feed_v1(self, tournament_slug=None, tournament_id=None, **kw):
        """Handle competition feed v1."""
        blocked_response = self._rate_limit_response("public_competition_feed")
        if blocked_response:
            return blocked_response
        tournament = self._resolve_tournament(
            tournament_slug=tournament_slug,
            tournament_id=tournament_id,
            public_access="detail",
        )
        if not tournament.exists():
            self._raise_not_found()
        return Response(
            json.dumps(tournament.get_public_feed_payload()),
            content_type="application/json; charset=utf-8",
            headers=[
                ("X-Federation-Contract", "tournament_feed"),
                ("X-Federation-Contract-Version", "v1"),
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
