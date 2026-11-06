"""Add several players to a roster in one step.

Clubs used to add players one form at a time and then press "Activate".  The
checklist below reuses the governed single-line path for every player and
activates the roster automatically once it satisfies the rules.
"""

from odoo import _, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .roster_portal import FederationRosterPortal


class FederationRosterBulkPortal(FederationRosterPortal):
    @http.route(
        ["/my/rosters/<int:roster_id>/lines/bulk"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def portal_my_roster_bulk_form(self, roster_id, **kw):
        try:
            roster = self._get_portal_roster(roster_id)
            roster._portal_assert_manage_access(user=request.env.user)
            players = request.env[
                "federation.team.roster.line"
            ]._portal_get_available_players(roster, user=request.env.user)
        except (AccessError, ValidationError):
            return self._render_access_denied()
        return request.render(
            "sports_federation_portal.portal_my_roster_bulk_add",
            {
                "roster": roster,
                "players": players,
                "page_name": "roster_bulk_add",
                "error": kw.get("error"),
            },
        )

    @http.route(
        ["/my/rosters/<int:roster_id>/lines/bulk"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_roster_bulk_create(self, roster_id, **kw):
        try:
            roster = self._get_portal_roster(roster_id)
        except AccessError:
            return self._render_access_denied()
        player_ids = request.httprequest.form.getlist("player_ids")
        try:
            created = request.env["federation.team.roster.line"]._portal_add_players(
                roster, player_ids, user=request.env.user
            )
        except AccessError:
            return self._render_access_denied()
        except ValidationError as exc:
            return self._redirect_with_query(
                f"/my/rosters/{roster.id}/lines/bulk", error=str(exc)
            )
        return self._redirect_roster(
            roster, success=_("%(count)s player(s) added.", count=len(created))
        )

    @http.route()
    def portal_my_roster_line_create(self, roster_id, **kw):
        response = super().portal_my_roster_line_create(roster_id, **kw)
        try:
            self._get_portal_roster(roster_id)._portal_auto_activate(
                user=request.env.user
            )
        except (AccessError, ValidationError):
            pass
        return response
