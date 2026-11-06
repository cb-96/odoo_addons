"""Game-day line-ups and per-match participation in the club portal.

A team prepares one line-up per game day, chosen from its season roster. Every
match that day shares it; at each match the coach only crosses out the players
who do not play.
"""

from odoo import _, http
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
                    error=_("Select players from this game-day line-up."),
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
