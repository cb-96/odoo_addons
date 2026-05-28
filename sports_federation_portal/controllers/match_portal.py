from odoo import fields, http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .roster_helpers import FederationRosterPortalBase


class FederationMatchPortal(FederationRosterPortalBase):
    """Match sheet and match-day portal routes."""

    def _portal_match_sheet_model(self):
        return request.env["federation.match.sheet"]

    def _portal_match_sheet_domain(self):
        return self._portal_match_sheet_model()._portal_get_domain(
            user=request.env.user
        )

    def _portal_match_sheet_by_id(self, sheet_id):
        return request.env["federation.portal.privilege"].portal_search_by_id(
            self._portal_match_sheet_model(),
            sheet_id,
            self._portal_match_sheet_domain(),
            user=request.env.user,
        )

    @http.route(
        ["/my/match-sheets", "/my/match-sheets/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_match_sheets(self, page=1, **kw):
        """List match sheets visible to the current portal user."""
        MatchSheet = self._portal_match_sheet_model()
        PortalPrivilege = request.env["federation.portal.privilege"]
        domain = self._portal_match_sheet_domain()
        if domain == [("id", "=", False)]:
            return self._redirect_with_query("/my/club")

        total = PortalPrivilege.portal_search_count(
            MatchSheet,
            domain,
            user=request.env.user,
        )
        pager = portal_pager(
            url="/my/match-sheets",
            total=total,
            page=page,
            step=20,
        )
        match_sheets = PortalPrivilege.portal_search(
            MatchSheet,
            domain,
            limit=20,
            offset=pager["offset"],
            order="match_id desc, id desc",
            user=request.env.user,
        )
        values = {
            "match_sheets": match_sheets,
            "pager": pager,
            "page_name": "my_match_sheets",
        }
        return request.render(
            "sports_federation_portal.portal_my_match_sheets",
            values,
        )

    @http.route(
        ["/my/match-sheets/<int:sheet_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_match_sheet_detail(self, sheet_id, **kw):
        """Render a single match sheet."""
        sheet = self._portal_match_sheet_by_id(sheet_id)
        if not sheet.exists():
            self._raise_not_found()
        try:
            sheet._portal_assert_review_access(user=request.env.user)
        except AccessError:
            return self._render_access_denied()

        club = sheet.team_id.club_id
        PortalPrivilege = request.env["federation.portal.privilege"]
        Representative = request.env["federation.club.representative"]
        available_coaches = (
            PortalPrivilege.portal_search(
                Representative,
                [
                    ("club_id", "=", club.id),
                    ("role_type_id.code", "=", "coach"),
                ],
                user=request.env.user,
            )
            if club
            else Representative.browse()
        )
        available_managers = (
            PortalPrivilege.portal_search(
                Representative,
                [
                    ("club_id", "=", club.id),
                ],
                user=request.env.user,
            )
            if club
            else Representative.browse()
        )

        available_rosters = (
            PortalPrivilege.portal_search(
                request.env["federation.team.roster"],
                [
                    ("team_id", "=", sheet.team_id.id),
                    ("status", "in", ("active", "draft")),
                ],
                user=request.env.user,
            )
            if sheet.team_id
            else request.env["federation.team.roster"].browse()
        )

        values = {
            "sheet": sheet,
            "page_name": "my_match_sheets",
            "success": kw.get("success"),
            "error": kw.get("error"),
            "error_hint": kw.get("error_hint"),
            "can_prepare_sheet": sheet.state != "locked",
            "can_edit_squad": sheet.state == "draft",
            "available_coaches": available_coaches,
            "available_managers": available_managers,
            "available_rosters": available_rosters,
            "roster_lines": (
                sheet.roster_id.line_ids
                if sheet.roster_id
                else request.env["federation.team.roster.line"].browse()
            ),
            "sheet_line_by_player": {
                line.player_id.id: line for line in sheet.line_ids
            },
        }
        return request.render(
            "sports_federation_portal.portal_my_match_sheet_detail",
            values,
        )

    @http.route(
        ["/my/match-sheets/<int:sheet_id>/prep"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_match_sheet_prepare(self, sheet_id, **kw):
        """Save match-sheet preparation data."""
        sheet = self._portal_match_sheet_by_id(sheet_id)
        if not sheet.exists():
            self._raise_not_found()

        try:
            sheet._portal_update_preparation(
                user=request.env.user,
                values={
                    "coach_id": kw.get("coach_id") or False,
                    "coach_name": kw.get("coach_name"),
                    "manager_id": kw.get("manager_id") or False,
                    "manager_name": kw.get("manager_name"),
                    "roster_id": kw.get("roster_id") or False,
                    "notes": kw.get("notes"),
                },
            )
            if kw.get("submit_sheet"):
                sheet._portal_action_submit(user=request.env.user)
        except AccessError:
            return self._render_access_denied()
        except ValidationError as exc:
            return self._redirect_with_query(
                f"/my/match-sheets/{sheet_id}",
                error=str(exc),
                error_hint="Check the squad contains the required number of eligible players and preparation details are complete.",
            )

        success_message = (
            "Match-day preparation saved and sheet submitted."
            if kw.get("submit_sheet")
            else "Match-day preparation saved."
        )
        return self._redirect_with_query(
            f"/my/match-sheets/{sheet_id}",
            success=success_message,
        )

    @http.route(
        ["/my/match-sheets/<int:sheet_id>/squad"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_match_sheet_squad(self, sheet_id, **kw):
        """Save squad player selection for a match sheet."""
        sheet = self._portal_match_sheet_by_id(sheet_id)
        if not sheet.exists():
            self._raise_not_found()
        try:
            sheet._portal_assert_review_access(user=request.env.user)
        except AccessError:
            return self._render_access_denied()

        form = request.httprequest.form
        selected_player_ids = []
        for pid in form.getlist("squad_player_ids"):
            try:
                selected_player_ids.append(int(pid))
            except (ValueError, TypeError):
                pass

        squad_data = []
        for player_id in selected_player_ids:
            role = form.get(f"player_{player_id}_role", "starter")
            is_captain = bool(form.get(f"player_{player_id}_captain"))
            jersey = (form.get(f"player_{player_id}_jersey") or "").strip()
            squad_data.append(
                {
                    "player_id": player_id,
                    "role": role,
                    "is_captain": is_captain,
                    "jersey_number": jersey or False,
                }
            )

        try:
            sheet._portal_sync_squad(squad_data, user=request.env.user)
        except AccessError:
            return self._render_access_denied()
        except ValidationError as exc:
            return self._redirect_with_query(
                f"/my/match-sheets/{sheet_id}",
                error=str(exc),
                error_hint="Check the squad composition meets match requirements and no player is listed twice.",
            )

        return self._redirect_with_query(
            f"/my/match-sheets/{sheet_id}",
            success="Squad saved.",
        )

    @http.route(
        ["/my/match-day", "/my/match-day/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_match_day(self, page=1, **kw):
        """List upcoming match-day sheets for the current user."""
        MatchSheet = self._portal_match_sheet_model()
        PortalPrivilege = request.env["federation.portal.privilege"]
        domain = self._portal_match_sheet_domain()
        if domain == [("id", "=", False)]:
            return self._redirect_with_query("/my/club")

        domain += [("match_kickoff", "!=", False)]
        total = PortalPrivilege.portal_search_count(
            MatchSheet,
            domain,
            user=request.env.user,
        )
        pager = portal_pager(
            url="/my/match-day",
            total=total,
            page=page,
            step=20,
        )
        match_day_sheets = PortalPrivilege.portal_search(
            MatchSheet,
            domain,
            limit=20,
            offset=pager["offset"],
            order="match_kickoff asc, id asc",
            user=request.env.user,
        )
        values = {
            "match_day_sheets": match_day_sheets,
            "pager": pager,
            "page_name": "my_match_day",
            "today": fields.Date.context_today(request.env["federation.match.sheet"]),
        }
        return request.render(
            "sports_federation_portal.portal_my_match_day",
            values,
        )
