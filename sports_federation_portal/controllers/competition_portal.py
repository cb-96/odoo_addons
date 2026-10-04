from odoo import _, fields, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request
from werkzeug.utils import redirect
from urllib.parse import urlencode

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
        user = request.env.user
        teams = request.env["federation.portal.scope"].teams(user=user)
        privilege = request.env["federation.portal.privilege"]
        Entry = request.env["federation.competition.entry"]
        entries = privilege.portal_search(
            Entry,
            [("team_id", "in", teams.ids)],
            user=user,
            order="create_date desc,id desc",
        )
        now = fields.Datetime.now()
        Window = request.env["federation.registration.window"]
        candidates = privilege.portal_search(
            Window,
            [
                ("state", "=", "open"),
                "|",
                ("date_open", "=", False),
                ("date_open", "<=", now),
                "|",
                ("date_close", "=", False),
                ("date_close", ">=", now),
            ],
            order="date_close asc,id asc",
            user=user,
        )
        windows = candidates.browse([])
        for window in candidates:
            eligible_teams = teams & window.division_id.search_eligible_teams(
                extra_domain=[("active", "=", True)]
            )
            active_entries = entries.filtered(
                lambda entry: entry.window_id == window
                and entry.state != "withdrawn"
            )
            available_teams = eligible_teams - active_entries.mapped("team_id")
            capacity_count = privilege.portal_search_count(
                Entry,
                [
                    ("window_id", "=", window.id),
                    ("state", "in", ("submitted", "approved")),
                ],
                user=user,
            )
            has_capacity = (
                not window.division_id.max_participants
                or capacity_count < window.division_id.max_participants
            )
            if available_teams and has_capacity:
                windows |= window
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
            if not window:
                raise ValidationError(_("The registration window was not found."))
            request.env["federation.competition.entry"]._portal_submit_entry(
                window.division_id,
                team,
                notes=kw.get("submission_note"),
                user=request.env.user,
                window=window,
            )
        except (AccessError, ValidationError, ValueError, TypeError) as exc:
            return redirect(
                "/my/competition-entries?" + urlencode({"error": str(exc)}),
                code=302,
            )
        return redirect("/my/competition-entries?success=Entry submitted", code=302)

    def _portal_find_competition_entry(self, entry_id):
        user = request.env.user
        teams = request.env["federation.portal.scope"].teams(user=user)
        return request.env["federation.portal.privilege"].portal_search_by_id(
            request.env["federation.competition.entry"],
            entry_id,
            [("team_id", "in", teams.ids)],
            user=user,
        )

    @http.route(
        ["/my/competition-entries/<int:entry_id>"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def portal_competition_entry_detail(self, entry_id, **kw):
        entry = self._portal_find_competition_entry(entry_id)
        if not entry:
            return self._not_found_or_denied()
        return request.render(
            "sports_federation_portal.portal_competition_entry_detail",
            {
                "entry": entry,
                "page_name": "my_competition_entries",
                "success": kw.get("success"),
                "error": kw.get("error"),
            },
        )

    @http.route(
        ["/my/competition-entries/<int:entry_id>/resubmit"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_resubmit_competition_entry(self, entry_id, submission_note="", **kw):
        entry = self._portal_find_competition_entry(entry_id)
        if not entry:
            return self._not_found_or_denied()
        try:
            entry.portal_resubmit(submission_note, user=request.env.user)
        except (AccessError, ValidationError, ValueError, TypeError) as exc:
            return redirect(
                f"/my/competition-entries/{entry.id}?"
                + urlencode({"error": str(exc)}),
                code=302,
            )
        return redirect(
            f"/my/competition-entries/{entry.id}?"
            + urlencode({"success": "Entry resubmitted"}),
            code=302,
        )

    @http.route(
        ["/my/competition-entries/<int:entry_id>/withdraw"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_withdraw_competition_entry(self, entry_id, **kw):
        entry = self._portal_find_competition_entry(entry_id)
        if not entry:
            return self._not_found_or_denied()
        try:
            entry.portal_withdraw(user=request.env.user)
        except (AccessError, ValidationError, ValueError, TypeError) as exc:
            return redirect(
                f"/my/competition-entries/{entry.id}?"
                + urlencode({"error": str(exc)}),
                code=302,
            )
        return redirect(
            f"/my/competition-entries/{entry.id}?"
            + urlencode({"success": "Entry withdrawn"}),
            code=302,
        )

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
