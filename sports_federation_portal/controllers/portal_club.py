from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .portal_helpers import FederationPortalBase


class FederationClubPortal(FederationPortalBase):
    """Club and team portal routes."""

    @http.route(
        ["/my/club"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_club(self, **kw):
        """Show the portal user's club information."""
        clubs = self._get_portal_clubs()
        if not clubs:
            return self._render_unassigned_club()

        club = clubs[0]
        teams = (
            request.env["federation.team"]
            .sudo()
            .search(
                [("club_id", "=", club.id)],
                order="name",
            )
        )
        values = {
            "club": club,
            "teams": teams,
            "page_name": "my_club",
        }
        return request.render("sports_federation_portal.portal_my_club", values)

    @http.route(
        ["/my/teams"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_teams(self, **kw):
        """Show the portal user's teams."""
        clubs = self._get_portal_clubs()
        if not clubs:
            return self._redirect_with_query("/my/club")

        teams = (
            request.env["federation.team"]
            .sudo()
            .search(
                [("club_id", "in", clubs.ids)],
                order="name",
            )
        )
        values = {
            "teams": teams,
            "clubs": clubs,
            "page_name": "my_teams",
            "success": kw.get("success"),
            "error": kw.get("error"),
            "error_hint": kw.get("error_hint"),
        }
        return request.render("sports_federation_portal.portal_my_teams", values)

    @http.route(
        ["/my/teams/new"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def portal_my_teams_new(self, **kw):
        """Render the create-team form."""
        clubs = self._get_portal_clubs()
        if not clubs:
            return self._redirect_with_query("/my/club")

        values = {
            "clubs": clubs,
            "page_name": "new_team",
            "error": kw.get("error"),
            "error_hint": kw.get("error_hint"),
        }
        return request.render("sports_federation_portal.portal_my_team_new", values)

    @http.route(
        ["/my/teams/new"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_teams_create(
        self, name, club_id, category=None, gender=None, email=None, phone=None, **kw
    ):
        """Create a team through the portal."""
        try:
            club_id = int(club_id)
        except (ValueError, TypeError):
            return self._redirect_with_query(
                "/my/teams/new", error="Invalid club selection"
            )

        try:
            club = request.env["federation.club"].sudo().browse(club_id)
            request.env["federation.team"]._portal_create_team(
                club,
                values={
                    "name": name,
                    "category": category,
                    "gender": gender,
                    "email": email,
                    "phone": phone,
                },
                user=request.env.user,
            )
        except (AccessError, ValidationError) as error:
            return self._redirect_with_query(
                "/my/teams/new",
                error=str(error),
                error_hint="Verify all required fields are filled in and the team code is unique for your club.",
            )

        return self._redirect_with_query(
            "/my/teams", success="Team created successfully"
        )

    # ------------------------------------------------------------------
    # Player management
    # ------------------------------------------------------------------

    @http.route(
        ["/my/players"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_players(self, gender=None, state=None, **kw):
        """Show the portal user's club members (players)."""
        clubs = self._get_portal_clubs()
        if not clubs:
            return self._redirect_with_query("/my/club")

        domain = [("club_id", "in", clubs.ids)]
        valid_genders = {"male", "female"}
        valid_states = {"active", "inactive", "suspended"}
        if gender and gender in valid_genders:
            domain.append(("gender", "=", gender))
        else:
            gender = ""
        if state and state in valid_states:
            domain.append(("state", "=", state))
        else:
            state = ""

        players = (
            request.env["federation.player"]
            .sudo()
            .search(domain, order="last_name, first_name")
        )
        values = {
            "players": players,
            "page_name": "my_players",
            "filter_gender": gender,
            "filter_state": state,
            "success": kw.get("success"),
            "error": kw.get("error"),
            "error_hint": kw.get("error_hint"),
        }
        return request.render("sports_federation_portal.portal_my_players", values)

    @http.route(
        ["/my/players/new"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def portal_my_players_new(self, **kw):
        """Render the add-player form."""
        clubs = self._get_portal_clubs()
        if not clubs:
            return self._redirect_with_query("/my/club")

        values = {
            "page_name": "new_player",
            "error": kw.get("error"),
            "error_hint": kw.get("error_hint"),
        }
        return request.render("sports_federation_portal.portal_my_player_new", values)

    @http.route(
        ["/my/players/new"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_players_create(
        self,
        first_name,
        last_name,
        birth_date=None,
        gender=None,
        email=None,
        phone=None,
        **kw,
    ):
        """Create a player through the portal."""
        clubs = self._get_portal_clubs()
        if not clubs:
            return self._redirect_with_query("/my/club")

        try:
            request.env["federation.player"]._portal_create_player(
                clubs[0],
                values={
                    "first_name": first_name,
                    "last_name": last_name,
                    "birth_date": birth_date,
                    "gender": gender,
                    "email": email,
                    "phone": phone,
                },
                user=request.env.user,
            )
        except (AccessError, ValidationError) as error:
            return self._redirect_with_query(
                "/my/players/new",
                error=str(error),
                error_hint="Verify all required player fields are filled in correctly.",
            )

        return self._redirect_with_query(
            "/my/players", success="Player added successfully"
        )
