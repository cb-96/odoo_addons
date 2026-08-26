from odoo import _, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request
from werkzeug.utils import redirect

from .portal_helpers import FederationPortalBase


class FederationPortalcurrent(FederationPortalBase):
    def _not_found_or_denied(self):
        return self._render_access_denied()

    @http.route(
        ["/my/competitions", "/my/competitions/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_competitions(self, page=1, **kw):
        cards = request.env["federation.portal.competition.queries"].list_cards(
            user=request.env.user
        )
        return request.render(
            "sports_federation_portal.portal_my_competitions",
            {"competition_cards": cards, "page_name": "my_competitions"},
        )

    @http.route(
        ["/my/competitions/<int:edition_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_competition_detail(self, edition_id, **kw):
        try:
            workspace = request.env["federation.portal.competition.queries"].detail(
                edition_id, user=request.env.user
            )
        except AccessError:
            return self._not_found_or_denied()
        return request.render(
            "sports_federation_portal.portal_my_competition_detail",
            {"workspace": workspace, "page_name": "my_competitions"},
        )

    @http.route(
        ["/my/competition-entries"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_competition_entries(self, **kw):
        teams = request.env["federation.portal.scope"].teams(user=request.env.user)
        entries = request.env["federation.competition.entry"].search(
            [("team_id", "in", teams.ids)], order="create_date desc,id desc"
        )
        windows = request.env["federation.registration.window"].search(
            [("state", "=", "open")], order="date_close asc,id asc"
        )
        return request.render(
            "sports_federation_portal.portal_my_competition_entries",
            {
                "entries": entries,
                "windows": windows,
                "teams": teams,
                "page_name": "my_competition_entries",
                "success": kw.get("success"),
                "error": kw.get("error"),
            },
        )

    @http.route(
        ["/my/competition-entries/new"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_create_competition_entry(self, window_id, team_id, **kw):
        try:
            window = (
                request.env["federation.registration.window"]
                .sudo()
                .browse(int(window_id))
                .exists()
            )
            team = request.env["federation.team"].sudo().browse(int(team_id)).exists()
            request.env["federation.portal.scope"].assert_team(
                team, user=request.env.user
            )
            if not window or window.state != "open":
                raise ValidationError(_("The registration window is not open."))
            if window.division_id.get_team_eligibility_error(team):
                raise ValidationError(
                    window.division_id.get_team_eligibility_error(team)
                )
            entry = request.env["federation.portal.privilege"].portal_create(
                request.env["federation.competition.entry"],
                {"window_id": window.id, "team_id": team.id},
                user=request.env.user,
            )
            request.env["federation.portal.privilege"].portal_call(
                entry,
                "action_submit",
                scope_domain=[("team_id", "=", team.id)],
                user=request.env.user,
            )
        except (AccessError, ValidationError, ValueError, TypeError) as exc:
            return redirect(f"/my/competition-entries?error={str(exc)}", code=302)
        return redirect("/my/competition-entries?success=Entry submitted", code=302)

    @http.route(["/my/match-days"], type="http", auth="user", website=True)
    def portal_my_matchdays(self, **kw):
        days = request.env["federation.portal.matchday.queries"].visible_matchdays(
            user=request.env.user
        )
        return request.render(
            "sports_federation_portal.portal_my_matchdays",
            {"matchdays": days, "page_name": "my_matchdays"},
        )

    @http.route(
        ["/my/match-days/<int:matchday_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_matchday_detail(self, matchday_id, **kw):
        try:
            workspace = request.env["federation.portal.matchday.queries"].detail(
                matchday_id, user=request.env.user
            )
        except AccessError:
            return self._not_found_or_denied()
        return request.render(
            "sports_federation_portal.portal_my_matchday_detail",
            {"workspace": workspace, "page_name": "my_matchdays"},
        )

    @http.route(
        ["/sports/match-days/<int:matchday_id>/operations"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_matchday_operations_page(self, matchday_id, **kw):
        try:
            workspace = request.env["federation.portal.matchday.queries"].detail(
                matchday_id, user=request.env.user, manager=True
            )
        except AccessError:
            return self._not_found_or_denied()
        return request.render(
            "sports_federation_portal.portal_matchday_operations_page",
            {
                "workspace": workspace,
                "page_name": "matchday_operations",
                "operations_load_path": (
                    f"/sports/match-days/{matchday_id}/operations/data"
                ),
                "operations_action_path_template": (
                    f"/sports/match-days/{matchday_id}/matches/__MATCH_ID__/action"
                ),
            },
        )

    @http.route(
        ["/sports/match-days/<int:matchday_id>/operations/data"],
        type="jsonrpc",
        auth="user",
        methods=["POST"],
        csrf=True,
    )
    def portal_matchday_operations_data(self, matchday_id, **kw):
        try:
            workspace = request.env["federation.portal.matchday.queries"].detail(
                matchday_id, user=request.env.user, manager=True
            )
        except AccessError:
            return {
                "ok": False,
                "error": {"type": "forbidden", "message": _("Access denied.")},
            }
        return {
            "ok": True,
            "payload": self._serialize_matchday_workspace(workspace),
        }

    def _serialize_matchday_workspace(self, workspace):
        day = workspace["matchday"]
        publication = workspace["publication"]
        return {
            "matchday": {
                "id": day.id,
                "name": day.display_name,
                "date": str(day.date or ""),
                "state": day.state,
                "venue": day.venue_id.display_name,
            },
            "publication": {
                "id": publication.id,
                "version": publication.version,
                "state": publication.state,
            },
            "session": (
                {
                    "id": workspace["session"].id,
                    "state": workspace["session"].state,
                }
                if workspace["session"]
                else False
            ),
            "matches": [
                {
                    "id": match.id,
                    "name": match.display_name,
                    "home_team": match.home_team_id.display_name,
                    "away_team": match.away_team_id.display_name,
                    "state": match.state,
                    "result_state": match.result_state,
                    "published_slot": match.published_slot_id.display_name,
                    "operational_slot": match.operational_slot_id.display_name,
                    "operational_status": match.operational_status,
                }
                for match in workspace["matches"]
            ],
            "courts": [
                {
                    "id": status.id,
                    "court": status.court_id.display_name,
                    "state": status.state,
                    "delay_minutes": status.delay_minutes,
                    "note": status.note or "",
                }
                for status in workspace["courts"]
            ],
            "incidents": [
                {
                    "id": incident.id,
                    "type": incident.incident_type,
                    "description": incident.description,
                    "resolved": incident.resolved,
                }
                for incident in workspace["incidents"]
            ],
            "deviations": [
                {
                    "id": deviation.id,
                    "match_id": deviation.match_id.id,
                    "type": deviation.deviation_type,
                    "reason": deviation.reason,
                }
                for deviation in workspace["deviations"]
            ],
        }

    @http.route(
        ["/sports/match-days/<int:matchday_id>/matches/<int:match_id>/action"],
        type="jsonrpc",
        auth="user",
        methods=["POST"],
        csrf=True,
    )
    def portal_matchday_action(self, matchday_id, match_id, **kw):
        try:
            workspace = request.env["federation.portal.matchday.queries"].detail(
                matchday_id, user=request.env.user, manager=True
            )
            match = workspace["matches"].filtered(lambda item: item.id == match_id)
            if not match:
                raise AccessError()
            privilege = request.env["federation.portal.privilege"]
            action = kw.get("action")
            if action == "start":
                privilege.portal_call(match, "action_start", user=request.env.user)
            elif action == "finish":
                privilege.portal_call(match, "action_done", user=request.env.user)
            elif action == "save_score":
                privilege.portal_write(
                    match,
                    {
                        "home_score": int(kw.get("home_score", 0)),
                        "away_score": int(kw.get("away_score", 0)),
                    },
                    user=request.env.user,
                )
            else:
                raise ValidationError(_("Unsupported match-day action."))
        except (AccessError, ValidationError, ValueError) as exc:
            return {
                "ok": False,
                "error": {
                    "type": "validation",
                    "message": str(exc) or _("Action failed."),
                },
            }
        return {"ok": True, "payload": self._serialize_matchday_workspace(workspace)}
