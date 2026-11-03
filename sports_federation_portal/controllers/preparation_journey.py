from odoo import http
from odoo.exceptions import AccessError
from ..context_scope import scoped_url
from odoo.http import request
from .roster_helpers import FederationRosterPortalBase


class ClubPreparationJourney(FederationRosterPortalBase):
    @http.route("/my/preparation", type="http", auth="user", website=True, methods=["GET"])
    def club_preparation(self, club=None, team=None, registration=None, **kw):
        user = request.env.user
        try:
            selected_club, selected_team, selected_registration = self._journey_scope(club, team, registration)
        except AccessError:
            return self._render_access_denied()
        roster_model = request.env["federation.team.roster"]
        registrations = roster_model._portal_get_confirmed_registrations(user=user)
        if selected_club:
            registrations = registrations.filtered(lambda r: r.team_id.club_id.id == selected_club)
        if selected_team and selected_team not in registrations.mapped('team_id').ids:
            return self._render_access_denied()
        if selected_registration and selected_registration not in registrations.ids:
            return self._render_access_denied()
        if selected_team:
            registrations = registrations.filtered(lambda r: r.team_id.id == selected_team)
        if selected_registration:
            registrations = registrations.filtered(lambda r: r.id == selected_registration)
        if (selected_team or selected_registration) and not registrations:
            return self._render_access_denied()
        rows = []
        for registration in registrations:
            roster = roster_model._portal_get_primary_roster_for_registration(registration, user=user)
            rows.append({"registration": registration, "roster": roster})
        sheet_model = request.env["federation.match.sheet"]
        sheet_domain = []
        if selected_club:
            sheet_domain.append(('team_id.club_id', '=', selected_club))
        if selected_team:
            sheet_domain.append(('team_id', '=', selected_team))
        sheets = request.env["federation.portal.privilege"].portal_search(
            sheet_model, sheet_model._portal_get_domain(user=user) + sheet_domain + [("state", "in", ("draft", "submitted")), ("match_id.state", "!=", "cancelled")],
            user=user, order="id", limit=100,
        )
        return request.render("sports_federation_portal.club_preparation_journey", {
            "rows": rows, "sheets": sheets, "page_name": "club_preparation",
            "journey_club": selected_club, "journey_team": selected_team,
            "journey_registration": selected_registration,
            "preparation_url": lambda path: scoped_url(path, selected_club, selected_team, selected_registration),
        })
