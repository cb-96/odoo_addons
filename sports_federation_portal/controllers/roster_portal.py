from odoo import http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .roster_helpers import FederationRosterPortalBase


class FederationRosterPortal(FederationRosterPortalBase):
    """Roster and roster-line portal routes."""

    @http.route(
        ["/my/rosters", "/my/rosters/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_rosters(self, page=1, **kw):
        """List rosters visible to the current user."""
        Roster = (
            request.env["federation.team.roster"].with_user(request.env.user).sudo()
        )
        domain = Roster._portal_get_scope_domain(user=request.env.user)
        if domain == [("id", "=", False)]:
            return self._redirect_with_query("/my/club")

        total = Roster.search_count(domain)
        pager = portal_pager(
            url="/my/rosters",
            total=total,
            page=page,
            step=20,
        )
        rosters = Roster.search(
            domain,
            limit=20,
            offset=pager["offset"],
            order="season_id desc, team_id, id desc",
        )
        confirmed_registrations = request.env[
            "federation.team.roster"
        ]._portal_get_confirmed_registrations(user=request.env.user)
        roster_opportunities = [
            {
                "registration": registration,
                "roster": request.env[
                    "federation.team.roster"
                ]._portal_get_primary_roster_for_registration(
                    registration,
                    user=request.env.user,
                ),
            }
            for registration in confirmed_registrations
        ]
        values = {
            "rosters": rosters,
            "roster_opportunities": roster_opportunities,
            "pager": pager,
            "page_name": "my_rosters",
            "success": kw.get("success"),
            "error": kw.get("error"),
        }
        return request.render("sports_federation_portal.portal_my_rosters", values)

    @http.route(
        ["/my/rosters/create/<int:registration_id>"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_roster_create(self, registration_id, **kw):
        """Create a roster for a confirmed season registration."""
        registration = (
            request.env["federation.season.registration"]
            .with_user(request.env.user)
            .sudo()
            .browse(registration_id)
        )
        if not registration.exists():
            return self._redirect_with_query(
                "/my/rosters",
                error="Season registration not found",
            )

        try:
            roster = request.env[
                "federation.team.roster"
            ]._portal_create_roster_for_registration(
                registration,
                user=request.env.user,
            )
        except (AccessError, ValidationError) as exc:
            return self._redirect_with_query("/my/rosters", error=str(exc))

        return self._redirect_roster(
            roster,
            success="Roster ready for editing in the portal.",
        )

    @http.route(
        ["/my/rosters/<int:roster_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_roster_detail(self, roster_id, **kw):
        """Render a single roster."""
        try:
            roster = self._get_portal_roster(roster_id)
        except AccessError:
            self._raise_not_found()

        can_manage_roster = False
        portal_manage_error = False
        try:
            roster._portal_assert_manage_access(user=request.env.user)
            can_manage_roster = True
        except ValidationError as exc:
            portal_manage_error = str(exc)

        values = {
            "roster": roster,
            "page_name": "my_rosters",
            "success": kw.get("success"),
            "error": kw.get("error"),
            "can_manage_roster": can_manage_roster,
            "can_edit_roster": can_manage_roster and roster.status != "closed",
            "portal_manage_error": portal_manage_error,
        }
        return request.render(
            "sports_federation_portal.portal_my_roster_detail",
            values,
        )

    @http.route(
        ["/my/rosters/<int:roster_id>/edit"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def portal_my_roster_edit(self, roster_id, **kw):
        """Render the roster edit form."""
        try:
            roster = self._get_portal_roster(roster_id)
            roster._portal_assert_manage_access(user=request.env.user)
        except AccessError:
            self._raise_not_found()
        except ValidationError as exc:
            return self._redirect_roster(roster, error=str(exc))

        values = {
            "roster": roster,
            "page_name": "my_rosters",
            "error": kw.get("error"),
        }
        return request.render(
            "sports_federation_portal.portal_my_roster_edit",
            values,
        )

    @http.route(
        ["/my/rosters/<int:roster_id>/edit"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_roster_update(self, roster_id, **kw):
        """Update a roster through the portal."""
        try:
            roster = self._get_portal_roster(roster_id)
            roster._portal_update_roster(
                user=request.env.user,
                values={
                    "name": kw.get("name"),
                    "valid_from": kw.get("valid_from"),
                    "valid_to": kw.get("valid_to"),
                    "notes": kw.get("notes"),
                },
            )
        except AccessError:
            self._raise_not_found()
        except ValidationError as exc:
            return self._redirect_with_query(
                f"/my/rosters/{roster_id}/edit",
                error=str(exc),
            )

        return self._redirect_roster(roster, success="Roster updated.")

    @http.route(
        ["/my/rosters/<int:roster_id>/activate"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_roster_activate(self, roster_id, **kw):
        """Activate a roster."""
        try:
            roster = self._get_portal_roster(roster_id)
            roster._portal_action_activate(user=request.env.user)
        except AccessError:
            self._raise_not_found()
        except ValidationError as exc:
            return self._redirect_roster(roster, error=str(exc))

        return self._redirect_roster(roster, success="Roster activated.")

    @http.route(
        ["/my/rosters/<int:roster_id>/draft"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_roster_set_draft(self, roster_id, **kw):
        """Move a roster back to draft."""
        try:
            roster = self._get_portal_roster(roster_id)
            roster._portal_action_set_draft(user=request.env.user)
        except AccessError:
            self._raise_not_found()
        except ValidationError as exc:
            return self._redirect_roster(roster, error=str(exc))

        return self._redirect_roster(roster, success="Roster set back to draft.")

    @http.route(
        ["/my/rosters/<int:roster_id>/close"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_roster_close(self, roster_id, **kw):
        """Close a roster."""
        try:
            roster = self._get_portal_roster(roster_id)
            roster._portal_action_close(user=request.env.user)
        except AccessError:
            self._raise_not_found()
        except ValidationError as exc:
            return self._redirect_roster(roster, error=str(exc))

        return self._redirect_roster(roster, success="Roster closed.")

    @http.route(
        ["/my/rosters/<int:roster_id>/lines/new"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def portal_my_roster_line_new(self, roster_id, **kw):
        """Render the new roster-line form."""
        try:
            roster = self._get_portal_roster(roster_id)
            roster._portal_assert_manage_access(user=request.env.user)
            line_model = request.env["federation.team.roster.line"]
            available_players = line_model._portal_get_available_players(
                roster,
                user=request.env.user,
            )
            available_licenses = line_model._portal_get_available_licenses(
                roster,
                user=request.env.user,
            )
        except AccessError:
            self._raise_not_found()
        except ValidationError as exc:
            return self._redirect_roster(roster, error=str(exc))

        return self._render_roster_line_form(
            roster,
            submit_url=f"/my/rosters/{roster.id}/lines/new",
            page_title="Add Roster Player",
            available_players=available_players,
            available_licenses=available_licenses,
            error=kw.get("error"),
        )

    @http.route(
        ["/my/rosters/<int:roster_id>/lines/new"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_roster_line_create(self, roster_id, **kw):
        """Create a roster line through the portal."""
        try:
            roster = self._get_portal_roster(roster_id)
            request.env["federation.team.roster.line"]._portal_create_line(
                roster,
                values=kw,
                user=request.env.user,
            )
        except AccessError:
            self._raise_not_found()
        except ValidationError as exc:
            return self._redirect_with_query(
                f"/my/rosters/{roster_id}/lines/new",
                error=str(exc),
            )

        return self._redirect_roster(roster, success="Player added to roster.")

    @http.route(
        ["/my/rosters/<int:roster_id>/lines/<int:line_id>/edit"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def portal_my_roster_line_edit(self, roster_id, line_id, **kw):
        """Render the roster-line edit form."""
        try:
            roster = self._get_portal_roster(roster_id)
            line = self._get_portal_roster_line(roster, line_id)
            roster._portal_assert_manage_access(user=request.env.user)
            if line.status != "active":
                return self._redirect_roster(
                    roster,
                    error="Only active roster lines can be edited in the portal.",
                )
            available_licenses = request.env[
                "federation.team.roster.line"
            ]._portal_get_available_licenses(
                roster,
                user=request.env.user,
                player=line.player_id,
            )
        except AccessError:
            self._raise_not_found()
        except ValidationError as exc:
            return self._redirect_roster(roster, error=str(exc))

        return self._render_roster_line_form(
            roster,
            line=line,
            submit_url=f"/my/rosters/{roster.id}/lines/{line.id}/edit",
            page_title="Edit Roster Player",
            available_licenses=available_licenses,
            error=kw.get("error"),
        )

    @http.route(
        ["/my/rosters/<int:roster_id>/lines/<int:line_id>/edit"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_roster_line_update(self, roster_id, line_id, **kw):
        """Update a roster line through the portal."""
        try:
            roster = self._get_portal_roster(roster_id)
            line = self._get_portal_roster_line(roster, line_id)
            line._portal_update_line(values=kw, user=request.env.user)
        except AccessError:
            self._raise_not_found()
        except ValidationError as exc:
            return self._redirect_with_query(
                f"/my/rosters/{roster_id}/lines/{line_id}/edit",
                error=str(exc),
            )

        return self._redirect_roster(roster, success="Roster line updated.")

    @http.route(
        ["/my/rosters/<int:roster_id>/lines/<int:line_id>/delete"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_roster_line_delete(self, roster_id, line_id, **kw):
        """Delete a roster line through the portal."""
        try:
            roster = self._get_portal_roster(roster_id)
            line = self._get_portal_roster_line(roster, line_id)
            line._portal_delete_line(user=request.env.user)
        except AccessError:
            self._raise_not_found()
        except ValidationError as exc:
            return self._redirect_roster(roster, error=str(exc))

        return self._redirect_roster(roster, success="Roster line removed.")
