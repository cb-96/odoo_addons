from urllib.parse import urlencode

from odoo import _, http
from odoo.addons.web.controllers.home import ensure_db
from odoo.addons.website.controllers.main import Website
from odoo.http import request


class FederationWebAuth(Website):
    """Override the core login route to recover from stale CSRF tokens."""

    def _redirect_to_login(self, redirect=None, login=None, session_expired=False):
        """Redirect to the login page with optional recovery context."""
        query = {}
        if redirect:
            query["redirect"] = redirect
        if login:
            query["login"] = login
        if session_expired:
            query["session_expired"] = "1"

        query_string = urlencode(query)
        target = "/web/login"
        if query_string:
            target = f"{target}?{query_string}"
        return request.redirect(target)

    @http.route(website=True, auth="public", sitemap=False, csrf=False)
    def web_login(self, redirect=None, **kw):
        """Recover gracefully when the login form is submitted with a stale CSRF token."""
        if request.httprequest.method == "POST":
            ensure_db()
            csrf_token = kw.get("csrf_token")
            if not csrf_token or not request.validate_csrf(csrf_token):
                return self._redirect_to_login(
                    redirect=kw.get("redirect") or redirect,
                    login=(kw.get("login") or "").strip() or None,
                    session_expired=True,
                )

        response = super().web_login(redirect=redirect, **kw)
        if hasattr(response, "qcontext") and request.params.get("session_expired"):
            response.qcontext["error"] = _(
                "Your session expired. Please sign in again and retry your last action."
            )
            if request.params.get("login"):
                response.qcontext["login"] = request.params.get("login")
        return response
