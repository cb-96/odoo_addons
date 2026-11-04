"""Gameday roster and per-match participation in the club portal.

A team prepares one roster per gameday. Every match that day shares it; at
each match the coach only crosses out the players who do not play.
"""

from odoo import _, http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .match_portal import FederationMatchPortal


class FederationGamedayParticipationPortal(FederationMatchPortal):
    def _portal_gameday_sheets(self, sheet):
        """Return the visible sheets sharing ``sheet``'s gameday roster."""
        gameday_ids = sheet._get_gameday_sheets().ids
        return request.env["federation.portal.privilege"].portal_search(
            self._portal_match_sheet_model(),
            self._portal_match_sheet_domain() + [("id", "in", gameday_ids)],
            order="match_kickoff asc, id asc",
            user=request.env.user,
        )

    _GAMEDAY_PAGE_SIZE = 20
    _GAMEDAY_SHEET_LIMIT = 2000

    @http.route()
    def portal_my_match_sheets(self, page=1, **kw):
        """One row per team gameday; grouped before paging so a gameday
        never appears on two pages."""
        MatchSheet = self._portal_match_sheet_model()
        Privilege = request.env["federation.portal.privilege"]
        domain = self._portal_match_sheet_domain()
        if domain == [("id", "=", False)]:
            return self._redirect_with_query("/my/club")
        try:
            context_domain, context_query = self._journey_list_scope(
                kw, season_field="roster_id.season_id"
            )
        except AccessError:
            return self._render_access_denied()
        sheets = Privilege.portal_search(
            MatchSheet,
            domain + context_domain,
            limit=self._GAMEDAY_SHEET_LIMIT,
            order="match_kickoff desc, id desc",
            user=request.env.user,
        )
        groups = {}
        for sheet in sheets:
            key = (sheet.team_id.id, sheet._get_gameday_scope() or ("sheet", sheet.id))
            groups.setdefault(key, MatchSheet.browse())
            groups[key] |= sheet
        ordered = list(groups.values())
        pager = portal_pager(
            url="/my/match-sheets",
            total=len(ordered),
            page=page,
            step=self._GAMEDAY_PAGE_SIZE,
            url_args=context_query,
        )
        page_groups = ordered[pager["offset"] : pager["offset"] + self._GAMEDAY_PAGE_SIZE]
        rows = MatchSheet.browse()
        match_counts = {}
        for group in page_groups:
            lead = group.sorted(lambda item: (item.match_kickoff or item.create_date, item.id))[:1]
            rows |= lead
            match_counts[lead.id] = len(group)
        return request.render(
            "sports_federation_portal.portal_my_match_sheets",
            {
                "match_sheets": rows,
                "gameday_match_counts": match_counts,
                "pager": pager,
                "page_name": "my_match_sheets",
            },
        )

    @http.route()
    def portal_my_match_sheet_detail(self, sheet_id, **kw):
        """Add the shared gameday matches to the sheet page."""
        response = super().portal_my_match_sheet_detail(sheet_id, **kw)
        qcontext = getattr(response, "qcontext", None)
        if qcontext and qcontext.get("sheet"):
            qcontext["gameday_sheets"] = self._portal_gameday_sheets(qcontext["sheet"])
        return response

    @http.route(
        ["/my/match-sheets/<int:sheet_id>/participation"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_match_sheet_participation(self, sheet_id, **kw):
        """Save which gameday players are crossed out for this match only."""
        sheet = self._portal_match_sheet_by_id(sheet_id)
        if not sheet.exists():
            self._raise_not_found()
        crossed_out = []
        for value in request.httprequest.form.getlist("crossed_out_player_ids"):
            try:
                crossed_out.append(int(value))
            except (TypeError, ValueError):
                return self._redirect_with_query(
                    f"/my/match-sheets/{sheet_id}",
                    error=_("Select players from this gameday roster."),
                )
        try:
            sheet._portal_set_participation(crossed_out, user=request.env.user)
        except AccessError:
            return self._render_access_denied()
        except ValidationError as exc:
            return self._redirect_with_query(
                f"/my/match-sheets/{sheet_id}",
                error=str(exc),
                error_hint=_(
                    "Cross out players until no more than the allowed number play."
                ),
            )
        return self._redirect_with_query(
            f"/my/match-sheets/{sheet_id}",
            success=_("Players for this match saved."),
        )
