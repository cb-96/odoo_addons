from odoo import http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .portal_helpers import FederationPortalBase

_NOMINATABLE_STATES = ("open", "rejected")


class FederationClubRefereeDutyPortal(FederationPortalBase):
    """Portal routes for club referee duty nomination flow."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _duty_portal_domain(self, user=None):
        """Return ORM domain for duties visible to *user*'s clubs."""
        user = user or request.env.user
        clubs = user.portal_club_scope_ids
        if not clubs:
            return [("id", "=", False)]
        return [
            ("club_id", "in", clubs.ids),
            ("state", "in", list(_NOMINATABLE_STATES) + ["nominated", "confirmed"]),
        ]

    def _assert_duty_access(self, duty, user=None):
        """Return True if *user* can access *duty*; raise AccessError otherwise."""
        user = user or request.env.user
        clubs = user.portal_club_scope_ids
        if duty.club_id not in clubs:
            raise AccessError(
                "You do not have access to this club duty."
            )
        return True

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @http.route(
        ["/my/referee-duties", "/my/referee-duties/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_referee_duties(self, page=1, **kw):
        """List club referee duties visible to the current portal user."""
        user = request.env.user
        Duty = request.env["federation.match.club.referee.duty"].sudo()

        domain = self._duty_portal_domain(user=user)
        if domain == [("id", "=", False)]:
            return self._render_unassigned_club()

        total = Duty.search_count(domain)
        pager = portal_pager(
            url="/my/referee-duties",
            total=total,
            page=page,
            step=20,
        )
        duties = Duty.search(
            domain,
            limit=20,
            offset=pager["offset"],
            order="nomination_deadline asc, id desc",
        )
        values = {
            "duties": duties,
            "pager": pager,
            "page_name": "my_referee_duties",
            "success": kw.get("success"),
            "error": kw.get("error"),
        }
        return request.render(
            "sports_federation_portal.portal_referee_duty_list",
            values,
        )

    @http.route(
        ["/my/referee-duties/<int:duty_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_referee_duty_detail(self, duty_id, **kw):
        """Show a single club referee duty with nomination form."""
        duty = request.env["federation.match.club.referee.duty"].sudo().browse(duty_id)
        if not duty.exists():
            self._raise_not_found()
        self._assert_duty_access(duty)

        # Build rostered player list for this club
        players = (
            request.env["federation.player"]
            .sudo()
            .search([("club_id", "=", duty.club_id.id)])
        )
        values = {
            "duty": duty,
            "players": players,
            "page_name": "my_referee_duties",
            "success": kw.get("success"),
            "error": kw.get("error"),
            "error_hint": kw.get("error_hint"),
        }
        return request.render(
            "sports_federation_portal.portal_referee_duty_form",
            values,
        )

    @http.route(
        ["/my/referee-duties/<int:duty_id>/nominate"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_nominate_duty(self, duty_id, player_id=None, **kw):
        """Submit nomination: club rep selects a player for the duty."""
        duty = request.env["federation.match.club.referee.duty"].sudo().browse(duty_id)
        if not duty.exists():
            self._raise_not_found()
        self._assert_duty_access(duty)

        if duty.state not in _NOMINATABLE_STATES:
            return self._redirect_with_query(
                f"/my/referee-duties/{duty_id}",
                error="This duty cannot be nominated in its current state.",
            )

        if not player_id:
            return self._redirect_with_query(
                f"/my/referee-duties/{duty_id}",
                error_hint="Please select a player before submitting.",
            )

        try:
            player_id = int(player_id)
        except (ValueError, TypeError):
            return self._redirect_with_query(
                f"/my/referee-duties/{duty_id}",
                error_hint="Invalid player selection.",
            )

        try:
            duty.with_user(request.env.user).sudo().action_nominate(player_id)
        except (ValidationError, AccessError) as exc:
            return self._redirect_with_query(
                f"/my/referee-duties/{duty_id}",
                error=str(exc),
            )

        return self._redirect_with_query(
            f"/my/referee-duties/{duty_id}",
            success="Your nomination has been submitted.",
        )
