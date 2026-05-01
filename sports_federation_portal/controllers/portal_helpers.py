from urllib.parse import urlencode

from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class FederationPortalBase(CustomerPortal):
    """Shared helpers for federation portal controllers."""

    def _raise_not_found(self):
        """Raise the framework 404 exception for hidden portal resources."""
        raise request.not_found()

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
