from odoo import http
from odoo.http import request

from .portal_helpers import FederationPortalBase


class FederationQolSearchPortal(FederationPortalBase):
    @http.route("/federation/search", type="http", auth="user", website=True)
    def federation_search(self, q="", **kw):
        results = request.env["federation.qol.search"].search_everywhere(q)
        return request.render(
            "sports_federation_portal.federation_qol_search_results",
            {"query": q, "results": results, "page_name": "federation_search"},
        )
