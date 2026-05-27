from urllib.parse import urlencode

from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class FederationPortalBase(CustomerPortal):
    """Shared helpers for federation portal controllers."""

    def _raise_not_found(self):
        """Raise the framework 404 exception for hidden portal resources."""
        raise request.not_found()

    def _render_access_denied(self):
        """Render a 403 Access Denied page for portal resources the user cannot access.

        Shows a generic message without leaking record ownership or content.
        """
        return request.render(
            "sports_federation_portal.portal_403_access_denied",
            {},
            status=403,
        )

    def _prepare_portal_layout_values(self):
        """Populate shared portal personas with elevated reads for safe layout render.

        Layout templates need representative and referee context even before a
        route has decided which portal persona is active, so these reads happen
        through controlled elevated access.
        """
        values = super()._prepare_portal_layout_values()
        representative = (
            request.env["federation.club.representative"]
            .sudo()
            .search(
                [("user_id", "=", request.env.user.id)],
                limit=1,
            )
        )
        referee = (
            request.env["federation.referee"]
            .with_user(request.env.user)
            .sudo()
            ._portal_get_for_user(user=request.env.user)
        )
        values["federation_representative"] = representative
        values["federation_club"] = representative.club_id if representative else None
        values["federation_referee"] = referee

        if referee and "federation.match.referee" in request.env:
            assignment_model = request.env["federation.match.referee"].sudo()
            assignment_domain = [("referee_id", "=", referee.id)]
            values["federation_pending_assignment_count"] = assignment_model.search_count(
                assignment_domain + [("state", "=", "draft")]
            )
            values["federation_overdue_assignment_count"] = assignment_model.search_count(
                assignment_domain
                + [("state", "=", "draft"), ("is_confirmation_overdue", "=", True)]
            )
        else:
            values["federation_pending_assignment_count"] = 0
            values["federation_overdue_assignment_count"] = 0

        # Count badges for portal home sidebar urgency indicators
        if representative:
            clubs = representative.mapped("club_id")
            club_ids = clubs.ids
            values["federation_pending_duties_count"] = (
                request.env["federation.match.club.referee.duty"]
                .sudo()
                .search_count([
                    ("club_id", "in", club_ids),
                    ("state", "in", ("open", "rejected")),
                ])
            )
            values["federation_pending_results_count"] = (
                request.env["federation.match.result"]
                .sudo()
                .search_count([
                    ("state", "=", "pending_approval"),
                    "|",
                    ("match_id.home_team_id.club_id", "in", club_ids),
                    ("match_id.away_team_id.club_id", "in", club_ids),
                ])
            ) if "federation.match.result" in request.env else 0
        else:
            values["federation_pending_duties_count"] = 0
            values["federation_pending_results_count"] = 0

        return values

    def _get_portal_clubs(self):
        """Return club scope derived from representative links for the current user."""
        return request.env["federation.club.representative"]._get_clubs_for_user()

    def _get_portal_default_domain(self):
        """Return the default domain for controllers that operate on club-owned data."""
        clubs = self._get_portal_clubs()
        return [("club_id", "in", clubs.ids)]

    def _redirect_with_query(self, path, **params):
        """Redirect with only meaningful query params so portal messages stay stable."""
        query = {
            key: value
            for key, value in params.items()
            if value not in (None, False, "")
        }
        if query:
            return request.redirect(f"{path}?{urlencode(query)}")
        return request.redirect(path)

    def _render_unassigned_club(self):
        """Render the canonical no-club-assignment state instead of surfacing ACL noise."""
        return request.render(
            "sports_federation_portal.portal_my_club",
            {
                "error": "You are not assigned as a club representative. Please contact the federation.",
            },
        )
