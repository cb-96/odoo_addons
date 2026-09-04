from odoo import http
from odoo.http import request

from .portal_helpers import FederationPortalBase


class FederationDataApiPortal(FederationPortalBase):
    @http.route("/my/data-api", type="http", auth="user", website=True)
    def data_api_tutorial(self, **kw):
        if not self._get_portal_clubs():
            return request.redirect("/my")

        base_url = request.httprequest.url_root.rstrip("/")
        editions = request.env[
            "federation.public.competition.queries"
        ].list_editions(archived=False)
        return request.render(
            "sports_federation_portal.portal_data_api_tutorial",
            {
                "page_name": "data_api",
                "base_url": base_url,
                "index_url": f"{base_url}/api/v1/competitions",
                "editions": editions,
            },
        )
