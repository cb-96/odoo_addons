"""Filter and domain-building helpers for public tournament hub routes.

Extracted from ``PublicTournamentHubController`` so that the main controller
module stays focused on routing and rendering.  Mix this class in first when
composing the controller.
"""

from odoo.http import request


class TournamentHubFilterMixin:
    """Mixin that provides filter parsing and domain building for hub routes."""

    # -- Request parameter parsing -------------------------------------------

    def _parse_int_param(self, value):
        """Parse int param."""
        try:
            return int(value) if value else False
        except (TypeError, ValueError):
            return False

    def _build_filters(self, search="", **kw):
        """Build a normalised filter dict from inbound request parameters."""
        return {
            "search": (search or kw.get("search") or "").strip(),
            "season_id": self._parse_int_param(kw.get("season_id")),
            "state": (kw.get("state") or "").strip(),
            "category": (kw.get("category") or "").strip(),
            "gender": (kw.get("gender") or "").strip(),
            "venue_id": self._parse_int_param(kw.get("venue_id")),
        }

    # -- Domain builders ------------------------------------------------------

    def _build_shared_filter_domain(self, filters):
        """Return the ORM domain clauses that are shared by hub sections."""
        Tournament = request.env["federation.tournament"]
        domain = []
        if filters["search"]:
            domain += Tournament._get_public_site_search_domain(filters["search"])
        if filters["season_id"]:
            domain.append(("season_id", "=", filters["season_id"]))
        if filters["category"]:
            domain.append(("category", "=", filters["category"]))
        if filters["gender"]:
            domain.append(("gender", "=", filters["gender"]))
        if filters["venue_id"] and "venue_id" in Tournament._fields:
            domain.append(("venue_id", "=", filters["venue_id"]))
        return domain

    def _build_main_tournament_domain(self, filters):
        """Return the ORM domain for the paginated tournaments list."""
        domain = [
            ("website_published", "=", True),
            ("state", "in", ("open", "in_progress", "closed", "cancelled")),
        ]
        domain += self._build_shared_filter_domain(filters)
        if filters["state"]:
            domain.append(("state", "=", filters["state"]))
        return domain

    def _build_tournament_public_domain(self, public_access=None):
        """Return the publication domain required for a public tournament route."""
        if not public_access:
            return []

        domain = [("website_published", "=", True)]
        if public_access == "results":
            domain.append(("show_public_results", "=", True))
        elif public_access == "standings":
            domain.append(("show_public_standings", "=", True))
        return domain

    def _build_season_public_domain(self, public_access=None):
        """Return the publication domain required for a public season route."""
        if not public_access:
            return []
        return [("website_published", "=", True)]

    def _build_team_public_domain(self, public_access=None):
        """Return the publication domain required for a public team route."""
        if not public_access:
            return []
        return [
            "|",
            "&",
            ("public_participant_ids.state", "!=", "withdrawn"),
            ("public_participant_ids.tournament_id.website_published", "=", True),
            "|",
            ("public_home_match_ids.tournament_id.website_published", "=", True),
            ("public_away_match_ids.tournament_id.website_published", "=", True),
        ]

    # -- Reference data for filter UI ----------------------------------------

    def _get_filter_reference_data(self):
        """Return seasons, venues, and selection-field options for filter widgets."""
        Tournament = request.env["federation.tournament"]
        return {
            "category_options": [("", "All Categories")]
            + list(Tournament._fields["category"].selection),
            "gender_options": [("", "All Genders")]
            + list(Tournament._fields["gender"].selection),
            "state_options": [
                ("", "All States"),
                ("open", "Open"),
                ("in_progress", "In Progress"),
                ("closed", "Closed"),
                ("cancelled", "Cancelled"),
            ],
            "seasons": request.env["federation.season"]
            .sudo()
            .search([], order="date_start desc, id desc"),
            "venues": (
                request.env["federation.venue"].sudo().search([], order="name asc")
                if "venue_id" in Tournament._fields
                else request.env["federation.venue"].browse([])
            ),
        }
