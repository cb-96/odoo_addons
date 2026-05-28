from odoo import http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.http import request


class PublicClubsController(http.Controller):

    def _raise_not_found(self):
        raise request.not_found()

    # ------------------------------------------------------------------
    # /clubs  — list
    # ------------------------------------------------------------------

    @http.route(
        ["/clubs", "/clubs/page/<int:page>"],
        type="http",
        auth="public",
        website=True,
    )
    def clubs_list(self, page=1, **kw):
        """Public list of website-published clubs."""
        Club = request.env["federation.club"].sudo()
        domain = [("website_published", "=", True)]
        step = 24
        total = Club.search_count(domain)
        pager = portal_pager(
            url="/clubs",
            total=total,
            page=page,
            step=step,
        )
        clubs = Club.search(
            domain, order="name asc", limit=step, offset=pager["offset"]
        )
        return request.render(
            "sports_federation_public_site.page_public_clubs_list",
            {"clubs": clubs, "pager": pager, "page_name": "public_clubs"},
        )

    # ------------------------------------------------------------------
    # /clubs/<slug>  — detail
    # ------------------------------------------------------------------

    @http.route(
        ["/clubs/<string:club_slug>"],
        type="http",
        auth="public",
        website=True,
    )
    def club_detail(self, club_slug, **kw):
        """Public club profile page."""
        club = request.env["federation.club"].resolve_public_slug(
            club_slug,
            extra_domain=[("website_published", "=", True)],
        )
        if not club.exists():
            self._raise_not_found()

        # Canonical redirect
        if club_slug != club.get_public_slug_value():
            return request.redirect(club.get_public_path())

        teams = club.team_ids.filtered(lambda t: t.active)
        recent_participations = club.get_recent_participations()

        return request.render(
            "sports_federation_public_site.page_public_club_detail",
            {
                "club": club,
                "teams": teams,
                "recent_participations": recent_participations,
                "page_name": "public_club_detail",
            },
        )

    # ------------------------------------------------------------------
    # /teams/<slug>  — detail (already handled by public_competitions.py
    # for teams with tournament participation; this is a fallback for
    # club-linked teams not yet in any tournament)
    # The existing route in public_competitions.py takes precedence.
    # ------------------------------------------------------------------


class PublicPlayersController(http.Controller):

    def _raise_not_found(self):
        raise request.not_found()

    # ------------------------------------------------------------------
    # /players  — list
    # ------------------------------------------------------------------

    @http.route(
        ["/players", "/players/page/<int:page>"],
        type="http",
        auth="public",
        website=True,
    )
    def players_list(self, page=1, **kw):
        """Public list of players with public_visible=True."""
        Player = request.env["federation.player"].sudo()
        domain = [("public_visible", "=", True)]
        step = 24
        total = Player.search_count(domain)
        pager = portal_pager(
            url="/players",
            total=total,
            page=page,
            step=step,
        )
        players = Player.search(
            domain,
            order="last_name asc, first_name asc",
            limit=step,
            offset=pager["offset"],
        )
        return request.render(
            "sports_federation_public_site.page_public_players_list",
            {"players": players, "pager": pager, "page_name": "public_players"},
        )

    # ------------------------------------------------------------------
    # /players/<slug>  — detail
    # ------------------------------------------------------------------

    @http.route(
        ["/players/<string:player_slug>"],
        type="http",
        auth="public",
        website=True,
    )
    def player_detail(self, player_slug, **kw):
        """Public player profile page."""
        player = request.env["federation.player"].resolve_public_slug(
            player_slug,
            extra_domain=[("public_visible", "=", True)],
        )
        if not player.exists():
            self._raise_not_found()

        # Canonical redirect
        if player_slug != player.get_public_slug_value():
            return request.redirect(player.get_public_path())

        licenses = player.license_ids.filtered(
            lambda lic: hasattr(lic, "state") and lic.state in ("active", "draft")
        )

        return request.render(
            "sports_federation_public_site.page_public_player_detail",
            {
                "player": player,
                "licenses": licenses,
                "page_name": "public_player_detail",
            },
        )
