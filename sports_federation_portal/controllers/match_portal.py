from odoo import http
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

    _GAMEDAY_PAGE_SIZE = 20
    _GAMEDAY_PAST_LIMIT = 20
    _GAMEDAY_SHEET_LIMIT = 2000

    @http.route(
        ["/my/match-sheets", "/my/match-sheets/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_match_sheets(self, page=1, **kw):
        """List the team game days: upcoming first, earlier ones collapsed.

        One row per team game day; grouped before paging so a game day never
        appears on two pages.
        """
        Privilege = request.env["federation.portal.privilege"]
        MatchSheet = self._portal_match_sheet_model()
        Gameday = request.env["federation.portal.gameday"]
        domain = self._portal_match_sheet_domain()
        if domain == [("id", "=", False)]:
            return self._redirect_with_query("/my/club")
        try:
            context_domain, context_query = self._journey_list_scope(
                kw, season_domain=Gameday.season_domain
            )
        except AccessError:
            return self._render_access_denied()
        scope = domain + context_domain
        upcoming_sheets = Privilege.portal_search(
            MatchSheet,
            scope + Gameday.upcoming_domain(),
            limit=self._GAMEDAY_SHEET_LIMIT,
            order="match_kickoff asc, id asc",
            user=request.env.user,
        )
        upcoming = Gameday.group_gamedays(upcoming_sheets, upcoming=True)
        total = len(upcoming)
        pager = portal_pager(
            url="/my/match-sheets",
            total=total,
            page=page,
            step=self._GAMEDAY_PAGE_SIZE,
            url_args=context_query,
        )
        page_rows = upcoming[
            pager["offset"] : pager["offset"] + self._GAMEDAY_PAGE_SIZE
        ]
        past_sheets = Privilege.portal_search(
            MatchSheet,
            scope + Gameday.past_domain(),
            limit=self._GAMEDAY_SHEET_LIMIT,
            order="match_kickoff desc, id desc",
            user=request.env.user,
        )
        past = Gameday.group_gamedays(past_sheets, upcoming=False)
        return request.render(
            "sports_federation_portal.portal_my_match_sheets",
            {
                "upcoming_gamedays": page_rows,
                "earlier_gamedays": past[: self._GAMEDAY_PAST_LIMIT],
                "earlier_total": len(past),
                "pager": pager,
                "page_name": "my_match_sheets",
            },
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

        Gameday = request.env["federation.portal.gameday"]
        available_rosters = Gameday.lineup_rosters(sheet, user=request.env.user)
        selected_roster = Gameday.default_lineup_roster(sheet, available_rosters)
        roster_lines = (
            selected_roster.line_ids
            if selected_roster
            else request.env["federation.team.roster.line"].browse()
        )
        # Back to the roster: the roster page lists the team's game days.
        back_roster = sheet.roster_id or selected_roster

        values = {
            "sheet": sheet,
            "page_name": "my_match_sheets",
            "success": kw.get("success"),
            "error": kw.get("error"),
            "error_hint": kw.get("error_hint"),
            # Approved and locked line-ups are read-only; submitted ones still
            # allow coach, manager and notes to be corrected.
            "can_prepare_sheet": sheet.state in ("draft", "submitted"),
            "can_edit_lineup": sheet.state == "draft",
            "available_coaches": available_coaches,
            "available_managers": available_managers,
            "available_rosters": available_rosters,
            "selected_roster": selected_roster,
            "back_url": (
                "/my/rosters/%s" % back_roster.id if back_roster else "/my/rosters"
            ),
            "roster_lines": roster_lines,
            "sheet_line_by_player": {
                line.player_id.id: line for line in sheet.line_ids
            },
            "lineup_state_label": Gameday.state_labels().get(
                Gameday.lineup_state(sheet)
            ),
        }
        return request.render(
            "sports_federation_portal.portal_my_match_sheet_detail",
            values,
        )

    @staticmethod
    def _lineup_players_from_form(form):
        """Read the selected game-day players and their details from the form."""
        players = []
        for pid in form.getlist("squad_player_ids"):
            try:
                player_id = int(pid)
            except (ValueError, TypeError):
                continue
            jersey = (form.get(f"player_{player_id}_jersey") or "").strip()
            players.append(
                {
                    "player_id": player_id,
                    "is_captain": bool(form.get(f"player_{player_id}_captain")),
                    "jersey_number": jersey or False,
                }
            )
        return players

    @http.route(
        ["/my/match-sheets/<int:sheet_id>/lineup"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_match_sheet_lineup(self, sheet_id, **kw):
        """Save roster, coach, manager and the game-day players in one step.

        The line-up is saved first; submitting is a separate step so a
        submission problem never throws away what the coach just filled in.
        """
        user = request.env.user
        sheet = self._portal_match_sheet_by_id(sheet_id)
        if not sheet.exists():
            self._raise_not_found()
        try:
            sheet._portal_assert_review_access(user=user)
        except AccessError:
            return self._render_access_denied()

        form = request.httprequest.form
        values = {
            "coach_id": kw.get("coach_id") or False,
            "coach_name": kw.get("coach_name"),
            "manager_id": kw.get("manager_id") or False,
            "manager_name": kw.get("manager_name"),
            "notes": kw.get("notes"),
        }
        # Only a draft line-up offers the roster choice; never clear it otherwise.
        roster_changed = False
        if "roster_id" in kw:
            values["roster_id"] = kw.get("roster_id") or False
            # The ticked players belong to the roster that was shown. When the
            # club picked another roster in the same submit, do not guess which
            # players carry over: save the roster and let them choose again.
            shown = (kw.get("shown_roster_id") or "").strip()
            roster_changed = bool(
                kw.get("roster_id") and shown and str(kw["roster_id"]).strip() != shown
            )
        try:
            with request.env.cr.savepoint():
                sheet._portal_update_preparation(values=values, user=user)
                if sheet.state == "draft" and form.get("has_lineup_players"):
                    players = (
                        [] if roster_changed else self._lineup_players_from_form(form)
                    )
                    sheet._portal_sync_squad(players, user=user)
        except AccessError:
            return self._render_access_denied()
        except ValidationError as exc:
            return self._redirect_with_query(
                f"/my/match-sheets/{sheet_id}",
                error=str(exc),
                error_hint="Choose a roster, then select the players for this game day within the allowed number.",
            )

        if roster_changed:
            return self._redirect_with_query(
                f"/my/match-sheets/{sheet_id}",
                success="Roster changed. Now choose the players for this game day.",
            )
        if not kw.get("submit_sheet"):
            return self._redirect_with_query(
                f"/my/match-sheets/{sheet_id}", success="Line-up saved."
            )
        try:
            with request.env.cr.savepoint():
                sheet._portal_action_submit(user=user)
        except AccessError:
            return self._render_access_denied()
        except ValidationError as exc:
            return self._redirect_with_query(
                f"/my/match-sheets/{sheet_id}",
                success="Line-up saved.",
                error=str(exc),
                error_hint="The line-up is saved but could not be submitted yet. Resolve the points above and submit again.",
            )
        return self._redirect_with_query(
            f"/my/match-sheets/{sheet_id}",
            success="Line-up saved and submitted for all matches on this game day.",
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
        """The old preparation queue is now the game-day list."""
        scope = {
            key: kw.get(key) for key in ("club", "team", "registration") if kw.get(key)
        }
        return self._redirect_with_query("/my/match-sheets", **scope)
