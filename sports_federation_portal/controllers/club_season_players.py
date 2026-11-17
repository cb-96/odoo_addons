from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .portal_helpers import FederationPortalBase


class FederationClubSeasonPlayersPortal(FederationPortalBase):
    def _registration(self, registration_id):
        clubs = self._get_portal_clubs()
        registration = (
            request.env["federation.club.season.registration"]
            .sudo()
            .search(
                [
                    ("id", "=", registration_id),
                    ("club_id", "in", clubs.ids),
                    ("company_id", "in", request.env.companies.ids),
                ],
                limit=1,
            )
        )
        if not registration:
            raise AccessError(request.env._("This club registration is not available."))
        return registration

    @http.route(
        "/my/season-players", type="http", auth="user", website=True, methods=["GET"]
    )
    def season_players(self, **kw):
        clubs = self._get_portal_clubs()
        if not clubs:
            return self._render_access_denied()
        return request.render(
            "sports_federation_portal.portal_season_players",
            {
                "registrations": request.env["federation.club.season.registration"]
                .sudo()
                .search(
                    [
                        ("club_id", "in", clubs.ids),
                        ("company_id", "in", request.env.companies.ids),
                    ]
                ),
                "clubs": clubs,
                "seasons": request.env["federation.season"]
                .sudo()
                .search([("state", "=", "open")]),
                "page_name": "season_players",
                "error": kw.get("error"),
            },
        )

    @http.route(
        "/my/season-players/start",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def start_registration(self, **kw):
        try:
            club_id, season_id = int(kw.get("club_id", 0)), int(kw.get("season_id", 0))
            clubs = self._get_portal_clubs()
            club = clubs.filtered(lambda item: item.id == club_id)
            season = (
                request.env["federation.season"]
                .sudo()
                .search(
                    [
                        ("id", "=", season_id),
                        ("state", "=", "open"),
                    ],
                    limit=1,
                )
            )
            if not club or not season:
                raise AccessError(request.env._("Select your club and an open season."))
            with request.env.cr.savepoint():
                registration = (
                    request.env["federation.club.season.registration"]
                    .sudo()
                    ._get_or_create(club, season)
                )
            if registration.company_id not in request.env.companies:
                raise AccessError(
                    request.env._("The registration company is not available.")
                )
            return request.redirect("/my/season-players/%s" % registration.id)
        except (ValueError, AccessError, ValidationError):
            return self._render_access_denied()

    @http.route(
        "/my/season-players/<int:registration_id>",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def registration_detail(self, registration_id, **kw):
        try:
            registration = self._registration(registration_id)
        except AccessError:
            return self._render_access_denied()
        existing = (
            request.env["federation.player.license"]
            .sudo()
            .search(
                [
                    ("season_id", "=", registration.season_id.id),
                    ("player_id.club_id", "=", registration.club_id.id),
                ]
            )
            .player_id
        )
        return request.render(
            "sports_federation_portal.portal_season_players_detail",
            {
                "registration": registration,
                "players": request.env["federation.player"]
                .sudo()
                .search(
                    [
                        ("club_id", "=", registration.club_id.id),
                        ("active", "=", True),
                        ("id", "not in", existing.ids),
                    ]
                ),
                "page_name": "season_players",
                "error": kw.get("error"),
            },
        )

    @http.route(
        "/my/season-players/<int:registration_id>/add",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def add_players(self, registration_id, **kw):
        try:
            registration = self._registration(registration_id)
            ids = set(
                int(value) for value in request.httprequest.form.getlist("player_ids")
            )
            players = (
                request.env["federation.player"]
                .sudo()
                .search(
                    [
                        ("id", "in", list(ids)),
                        ("club_id", "=", registration.club_id.id),
                        ("active", "=", True),
                    ]
                )
            )
            if not ids or set(players.ids) != ids:
                raise AccessError(
                    request.env._("Select players belonging to your club.")
                )
            with request.env.cr.savepoint():
                registration._add_players(players)
        except (AccessError, ValueError):
            return self._render_access_denied()
        except ValidationError as error:
            return self._redirect_with_query(
                "/my/season-players/%s" % registration_id, error=str(error)
            )
        return request.redirect("/my/season-players/%s" % registration_id)

    @http.route(
        "/my/season-players/<int:registration_id>/submit",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def submit_players(self, registration_id, **kw):
        try:
            registration = self._registration(registration_id)
            with request.env.cr.savepoint():
                registration.action_submit()
        except AccessError:
            return self._render_access_denied()
        except ValidationError as error:
            return self._redirect_with_query(
                "/my/season-players/%s" % registration_id, error=str(error)
            )
        return request.redirect("/my/season-players/%s" % registration_id)
