from odoo.exceptions import AccessError
from odoo.http import request

from .portal_helpers import FederationPortalBase


class FederationRosterPortalBase(FederationPortalBase):
    """Shared helpers for roster and match-day portal routes."""

    def _get_portal_roster(self, roster_id):
        """Return a roster visible to the current portal user."""
        portal_privilege = request.env["federation.portal.privilege"]
        roster_model = request.env["federation.team.roster"]
        roster = portal_privilege.portal_search_by_id(
            roster_model,
            roster_id,
            roster_model._portal_get_scope_domain(user=request.env.user),
            user=request.env.user,
        )
        if not roster:
            raise AccessError("Roster not found")
        return roster

    def _get_portal_roster_line(self, roster, line_id):
        """Return a roster line bound to the given roster."""
        line = request.env["federation.portal.privilege"].portal_search_by_id(
            request.env["federation.team.roster.line"],
            line_id,
            [("roster_id", "=", roster.id)],
            user=request.env.user,
        )
        if not line:
            raise AccessError("Roster line not found")
        return line

    def _redirect_roster(self, roster, success=None, error=None, error_hint=None):
        """Redirect back to a roster detail page with optional status messages."""
        return self._redirect_with_query(
            f"/my/rosters/{roster.id}",
            success=success,
            error=error,
            error_hint=error_hint,
        )

    def _render_roster_line_form(
        self,
        roster,
        submit_url,
        page_title,
        line=False,
        available_players=False,
        available_licenses=False,
        error=None,
        error_hint=None,
    ):
        """Render the roster line form with shared template values."""
        values = {
            "roster": roster,
            "line": line,
            "available_players": available_players,
            "available_licenses": available_licenses,
            "submit_url": submit_url,
            "page_title": page_title,
            "page_name": "my_rosters",
            "error": error,
            "error_hint": error_hint,
        }
        return request.render(
            "sports_federation_portal.portal_my_roster_line_form",
            values,
        )
