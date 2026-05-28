from odoo import http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.http import request

from .portal_helpers import FederationPortalBase


class FederationWorkspacePortal(FederationPortalBase):
    """Tournament workspace portal routes."""

    @http.route(
        ["/my/tournament-workspaces", "/my/tournament-workspaces/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tournament_workspaces(self, page=1, **kw):
        """List tournament workspace entries for the current user."""
        Tournament = request.env["federation.tournament"]
        entries = Tournament._portal_get_workspace_entries(user=request.env.user)
        step = 12
        pager = portal_pager(
            url="/my/tournament-workspaces",
            total=len(entries),
            page=page,
            step=step,
        )
        values = {
            "workspace_entries": entries[pager["offset"] : pager["offset"] + step],
            "pager": pager,
            "page_name": "my_tournament_workspaces",
            "has_workspace_access": Tournament._portal_has_workspace_access(
                user=request.env.user,
            ),
        }
        return request.render(
            "sports_federation_portal.portal_my_tournament_workspaces",
            values,
        )

    @http.route(
        ["/my/tournament-workspaces/<int:tournament_id>/<int:team_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tournament_workspace_detail(self, tournament_id, team_id, **kw):
        """Render a single tournament workspace entry."""
        workspace_entry = request.env[
            "federation.tournament"
        ]._portal_get_workspace_entry_for_user(
            tournament_id,
            team_id,
            user=request.env.user,
        )
        if not workspace_entry:
            self._raise_not_found()

        values = {
            "workspace": workspace_entry,
            "page_name": "my_tournament_workspaces",
        }
        return request.render(
            "sports_federation_portal.portal_my_tournament_workspace_detail",
            values,
        )
