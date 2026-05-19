from odoo import http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import ValidationError
from odoo.http import request

from .portal_helpers import FederationPortalBase

_VISIBLE_RESULT_STATES = ("submitted", "verified", "approved", "contested")


class FederationResultPortal(FederationPortalBase):
    """Portal routes for match result approval and contest flow."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _result_portal_domain(self, user=None):
        """Return ORM domain for matches whose result is visible to *user*."""
        user = user or request.env.user
        clubs = user.portal_club_scope_ids
        if not clubs:
            return [("id", "=", False)]
        return [
            ("result_state", "in", list(_VISIBLE_RESULT_STATES)),
            "|",
            ("home_team_id.club_id", "in", clubs.ids),
            ("away_team_id.club_id", "in", clubs.ids),
        ]

    def _assert_result_access(self, match, user=None):
        """Return True if *user* has portal access to *match*; False otherwise."""
        user = user or request.env.user
        clubs = user.portal_club_scope_ids
        return (
            match.home_team_id.club_id in clubs
            or match.away_team_id.club_id in clubs
        )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @http.route(
        ["/my/results", "/my/results/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_results(self, page=1, **kw):
        """List match results visible to the current portal user."""
        user = request.env.user
        Match = request.env["federation.match"].sudo()

        domain = self._result_portal_domain(user=user)
        if domain == [("id", "=", False)]:
            return self._redirect_with_query(
                "/my/club",
                error="You are not assigned as a club representative.",
            )

        total = Match.search_count(domain)
        pager = portal_pager(
            url="/my/results",
            total=total,
            page=page,
            step=20,
        )
        matches = Match.search(
            domain,
            limit=20,
            offset=pager["offset"],
            order="date_scheduled desc, id desc",
        )
        values = {
            "matches": matches,
            "pager": pager,
            "page_name": "my_results",
            "success": kw.get("success"),
            "error": kw.get("error"),
            "error_hint": kw.get("error_hint"),
        }
        return request.render(
            "sports_federation_portal.portal_my_results",
            values,
        )

    @http.route(
        ["/my/results/<int:match_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_result_detail(self, match_id, **kw):
        """Show a single match result."""
        match = request.env["federation.match"].sudo().browse(match_id)
        if not match.exists():
            self._raise_not_found()
        if not self._assert_result_access(match):
            return self._render_access_denied()

        values = {
            "match": match,
            "page_name": "my_results",
            "success": kw.get("success"),
            "error": kw.get("error"),
            "error_hint": kw.get("error_hint"),
        }
        return request.render(
            "sports_federation_portal.portal_my_result_detail",
            values,
        )

    @http.route(
        ["/my/results/<int:match_id>/approve"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_result_approve(self, match_id, **kw):
        """Club representative approves a verified result."""
        match = request.env["federation.match"].sudo().browse(match_id)
        if not match.exists():
            self._raise_not_found()
        if not self._assert_result_access(match):
            return self._render_access_denied()

        if match.result_state != "verified":
            return self._redirect_with_query(
                f"/my/results/{match_id}",
                error="Only verified results can be approved.",
            )

        try:
            match.action_approve_result()
        except ValidationError as exc:
            return self._redirect_with_query(
                f"/my/results/{match_id}",
                error=str(exc.args[0]) if exc.args else "Approval failed.",
            )

        return self._redirect_with_query(
            f"/my/results/{match_id}",
            success="Result approved successfully.",
        )

    @http.route(
        ["/my/results/<int:match_id>/contest"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_result_contest(self, match_id, **kw):
        """Club representative contests a submitted, verified, or approved result."""
        match = request.env["federation.match"].sudo().browse(match_id)
        if not match.exists():
            self._raise_not_found()
        if not self._assert_result_access(match):
            return self._render_access_denied()

        if match.result_state not in ("submitted", "verified", "approved"):
            return self._redirect_with_query(
                f"/my/results/{match_id}",
                error="Only submitted, verified, or approved results can be contested.",
                error_hint=(
                    "This result has already been contested."
                    if match.result_state == "contested"
                    else None
                ),
            )

        reason = (kw.get("result_contest_reason") or "").strip()
        if not reason:
            return self._redirect_with_query(
                f"/my/results/{match_id}",
                error="A contest reason is required.",
            )

        try:
            match.write({"result_contest_reason": reason})
            match.action_contest_result()
        except ValidationError as exc:
            return self._redirect_with_query(
                f"/my/results/{match_id}",
                error=str(exc.args[0]) if exc.args else "Contest failed.",
            )

        return self._redirect_with_query(
            f"/my/results/{match_id}",
            success="Result contested. The federation has been notified.",
        )
