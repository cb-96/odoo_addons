from odoo import http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .portal_helpers import FederationPortalBase


class FederationRegistrationPortal(FederationPortalBase):
    """Registration-focused portal routes."""

    @http.route(
        ["/my/season-registrations", "/my/season-registrations/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_season_registrations(self, page=1, **kw):
        """Show season registrations for the user's club."""
        clubs = self._get_portal_clubs()
        if not clubs:
            return self._redirect_with_query("/my/club")

        domain = [("club_id", "in", clubs.ids)]
        Registration = request.env["federation.season.registration"].sudo()
        total = Registration.search_count(domain)
        step = 20
        pager = portal_pager(
            url="/my/season-registrations",
            total=total,
            page=page,
            step=step,
        )
        registrations = Registration.search(
            domain,
            limit=step,
            offset=pager["offset"],
            order="create_date desc",
        )
        values = {
            "registrations": registrations,
            "pager": pager,
            "page_name": "my_season_registrations",
            "success": kw.get("success"),
            "error": kw.get("error"),
        }
        return request.render(
            "sports_federation_portal.portal_my_season_registrations",
            values,
        )

    @http.route(
        [
            "/my/tournament-registrations",
            "/my/tournament-registrations/page/<int:page>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tournament_registrations(self, page=1, **kw):
        """Show tournament registrations for the user's club."""
        clubs = self._get_portal_clubs()
        if not clubs:
            return self._redirect_with_query("/my/club")

        domain = [("club_id", "in", clubs.ids)]
        Registration = request.env["federation.tournament.registration"].sudo()
        total = Registration.search_count(domain)
        step = 20
        pager = portal_pager(
            url="/my/tournament-registrations",
            total=total,
            page=page,
            step=step,
        )
        registrations = Registration.search(
            domain,
            limit=step,
            offset=pager["offset"],
            order="create_date desc",
        )
        values = {
            "registrations": registrations,
            "pager": pager,
            "page_name": "my_tournament_registrations",
            "success": kw.get("success"),
            "error": kw.get("error"),
        }
        return request.render(
            "sports_federation_portal.portal_my_tournament_registrations",
            values,
        )

    @http.route(
        ["/my/season-registration/new"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def portal_season_registration_form(self, **kw):
        """Show the season registration form."""
        clubs = self._get_portal_clubs()
        if not clubs:
            return self._redirect_with_query("/my/club")

        teams = (
            request.env["federation.team"]
            .sudo()
            .search(
                [("club_id", "in", clubs.ids)],
                order="name",
            )
        )
        seasons = (
            request.env["federation.season"]
            .sudo()
            .search(
                [("state", "=", "open")],
                order="date_start desc",
            )
        )
        # Support pre-selecting a team when linked from /my/teams
        try:
            preselect_team_id = int(kw.get("team_id", 0)) or None
        except (ValueError, TypeError):
            preselect_team_id = None
        values = {
            "teams": teams,
            "seasons": seasons,
            "preselect_team_id": preselect_team_id,
            "page_name": "new_season_registration",
            "error": kw.get("error"),
        }
        return request.render(
            "sports_federation_portal.portal_season_registration_form",
            values,
        )

    @http.route(
        ["/my/season-registration/new"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_season_registration_submit(self, team_id, season_id, notes="", **kw):
        """Submit a season registration request."""
        try:
            team_id = int(team_id)
            season_id = int(season_id)
        except (ValueError, TypeError):
            return self._redirect_with_query(
                "/my/season-registration/new", error="Invalid selection"
            )

        try:
            request.env[
                "federation.season.registration"
            ]._portal_submit_registration_request(
                request.env["federation.season"].sudo().browse(season_id),
                request.env["federation.team"].sudo().browse(team_id),
                notes=notes,
                user=request.env.user,
            )
        except (AccessError, ValidationError) as error:
            return self._redirect_with_query(
                "/my/season-registration/new", error=str(error)
            )

        return self._redirect_with_query(
            "/my/season-registrations",
            success="Season registration submitted",
        )

    @http.route(
        ["/my/tournament-registration/<int:reg_id>/cancel"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_tournament_registration_cancel(self, reg_id, **kw):
        """Cancel a tournament registration."""
        clubs = self._get_portal_clubs()
        registration = (
            request.env["federation.tournament.registration"].sudo().browse(reg_id)
        )
        if not registration.exists() or registration.club_id not in clubs:
            return self._redirect_with_query(
                "/my/tournament-registrations",
                error="Registration not found",
            )

        try:
            registration.action_cancel()
        except ValidationError as error:
            return self._redirect_with_query(
                "/my/tournament-registrations",
                error=str(error),
            )

        return self._redirect_with_query(
            "/my/tournament-registrations",
            success="Registration cancelled",
        )

    @http.route(
        ["/my/season-registration/<int:reg_id>/cancel"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_season_registration_cancel(self, reg_id, **kw):
        """Cancel a season registration."""
        clubs = self._get_portal_clubs()
        registration = (
            request.env["federation.season.registration"].sudo().browse(reg_id)
        )
        if not registration.exists() or registration.club_id not in clubs:
            return self._redirect_with_query(
                "/my/season-registrations",
                error="Registration not found",
            )

        try:
            registration.action_cancel()
        except ValidationError as error:
            return self._redirect_with_query(
                "/my/season-registrations",
                error=str(error),
            )

        return self._redirect_with_query(
            "/my/season-registrations",
            success="Registration cancelled",
        )
