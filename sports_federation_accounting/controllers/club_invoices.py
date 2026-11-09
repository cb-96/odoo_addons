"""Club invoices in the portal: what the club owes and a link to pay it."""

from odoo import http
from odoo.http import request

from odoo.addons.sports_federation_portal.controllers.portal_helpers import (
    FederationPortalBase,
)


class FederationClubInvoices(FederationPortalBase):
    @http.route(
        ["/my/club-invoices"], type="http", auth="user", website=True, methods=["GET"]
    )
    def portal_club_invoices(self, **kw):
        user = request.env.user
        if not user.portal_club_scope_ids:
            return self._render_access_denied()
        values = self._prepare_portal_layout_values()
        values.update(
            {
                "rows": request.env[
                    "federation.finance.event"
                ]._portal_club_invoice_rows(user=user),
                "page_name": "club_invoices",
            }
        )
        return request.render("sports_federation_accounting.portal_club_invoices", values)
