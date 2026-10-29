from odoo import http
from odoo.http import request
from .roster_helpers import FederationRosterPortalBase


class ClubPreparationJourney(FederationRosterPortalBase):
    @http.route("/my/preparation", type="http", auth="user", website=True, methods=["GET"])
    def club_preparation(self, **kw):
        user = request.env.user
        roster_model = request.env["federation.team.roster"]
        registrations = roster_model._portal_get_confirmed_registrations(user=user)
        rows = []
        for registration in registrations:
            roster = roster_model._portal_get_primary_roster_for_registration(registration, user=user)
            rows.append({"registration": registration, "roster": roster})
        sheet_model = request.env["federation.match.sheet"]
        sheets = request.env["federation.portal.privilege"].portal_search(
            sheet_model, sheet_model._portal_get_domain(user=user) + [("state", "in", ("draft", "submitted")), ("match_id.state", "!=", "cancelled")],
            user=user, order="id", limit=100,
        )
        return request.render("sports_federation_portal.club_preparation_journey", {
            "rows": rows, "sheets": sheets, "page_name": "club_preparation",
        })
