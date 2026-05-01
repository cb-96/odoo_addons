from odoo import _, api, fields, models


class FederationTournament(models.Model):
    _inherit = "federation.tournament"

    _portal_workspace_active_states = ("open", "in_progress")
    _portal_workspace_result_follow_up_states = (
        "draft",
        "submitted",
        "verified",
        "contested",
        "corrected",
    )

    registration_request_ids = fields.One2many(
        "federation.tournament.registration",
        "tournament_id",
        string="Registration Requests",
    )
    registration_request_count = fields.Integer(
        string="Registration Request Count",
        compute="_compute_registration_request_count",
    )

    @api.depends("registration_request_ids")
    def _compute_registration_request_count(self):
        """Compute registration request count."""
        for tournament in self:
            tournament.registration_request_count = len(
                tournament.registration_request_ids
            )

    def action_view_registration_requests(self):
        """Execute the view registration requests action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_portal.action_federation_tournament_registration"
        )
        action["domain"] = [("tournament_id", "=", self.id)]
        action["context"] = {"default_tournament_id": self.id}
        return action

    @api.model
    def _portal_get_workspace_team_domain(self, user=None):
        """Handle the portal-specific get workspace team domain flow."""
        user = user or self.env.user
        club_scope = user.portal_club_scope_ids
        team_scope = user.portal_team_scope_ids
        if team_scope and club_scope:
            return [
                "|",
                ("id", "in", team_scope.ids),
                ("club_id", "in", club_scope.ids),
            ]
        if team_scope:
            return [("id", "in", team_scope.ids)]
        if club_scope:
            return [("club_id", "in", club_scope.ids)]
        return [("id", "=", False)]

    @api.model
    def _portal_has_workspace_access(self, user=None):
        """Handle the portal-specific has workspace access flow."""
        return self._portal_get_workspace_team_domain(user=user) != [("id", "=", False)]

    @api.model
    def _portal_get_workspace_tournament_domain(self):
        """Return the active tournament domain for portal workspace reads."""
        return [("state", "in", self._portal_workspace_active_states)]

    def _portal_assert_workspace_access(self, team, user=None):
        """Recheck team and tournament scope before elevated workspace reads."""
        self.ensure_one()
        user = user or self.env.user
        PortalPrivilege = self.env["federation.portal.privilege"]
        tournament = PortalPrivilege.portal_assert_in_domain(
            self,
            self._portal_get_workspace_tournament_domain(),
            _("You can only access active tournament workspaces."),
            user=user,
        )
        team = PortalPrivilege.portal_assert_in_domain(
            team,
            self._portal_get_workspace_team_domain(user=user),
            _(
                "You can only access tournament workspaces for your assigned teams or clubs."
            ),
            user=user,
        )
        team.ensure_one()
        return tournament, team

    def _portal_get_registration_checkpoint(self, registration, participant):
        """Handle the portal-specific get registration checkpoint flow."""
        self.ensure_one()
        if participant and participant.state == "confirmed":
            return {
                "label": _("Participant confirmed"),
                "tone": "success",
                "detail": _(
                    "The team is fully confirmed in this tournament and can continue operational preparation."
                ),
            }
        if registration and registration.state == "confirmed":
            return {
                "label": _("Registration confirmed"),
                "tone": "success",
                "detail": _(
                    "The federation has confirmed the registration and created the tournament participation record."
                ),
            }
        if participant and participant.state == "registered":
            return {
                "label": _("Participant record created"),
                "tone": "info",
                "detail": _(
                    "The team has a tournament participant record but is still awaiting final confirmation."
                ),
            }
        if registration and registration.state == "submitted":
            return {
                "label": _("Registration under review"),
                "tone": "warning",
                "detail": _(
                    "The tournament registration has been submitted and is waiting for federation review."
                ),
            }
        if registration and registration.state == "rejected":
            detail = registration.rejection_reason or _(
                "Review the rejection feedback and resubmit when the issue has been addressed."
            )
            return {
                "label": _("Registration rejected"),
                "tone": "danger",
                "detail": detail,
            }
        if participant and participant.state == "withdrawn":
            return {
                "label": _("Participation withdrawn"),
                "tone": "secondary",
                "detail": _(
                    "This team was previously linked to the tournament but is now withdrawn from competition."
                ),
            }
        if self.state == "open":
            return {
                "label": _("Registration not submitted"),
                "tone": "secondary",
                "detail": _(
                    "No active tournament registration is currently linked to this team for the open tournament."
                ),
            }
        return {
            "label": _("No registration record"),
            "tone": "secondary",
            "detail": _(
                "The workspace is being shown because the team already has operational records in this tournament."
            ),
        }

    def _portal_get_roster_checkpoint(self, roster):
        """Handle the portal-specific get roster checkpoint flow."""
        self.ensure_one()
        if not roster:
            return {
                "label": _("Roster missing"),
                "tone": "danger",
                "detail": _(
                    "Create or link a season or competition roster before match-day activity starts."
                ),
            }
        if roster.match_day_locked:
            return {
                "label": _("Roster frozen by match-day activity"),
                "tone": "info",
                "detail": roster.match_day_lock_feedback
                or _(
                    "At least one match sheet has already left draft, so the roster scope is locked for audit consistency."
                ),
            }
        if roster.status == "active" and roster.ready_for_activation:
            return {
                "label": _("Roster active"),
                "tone": "success",
                "detail": _(
                    "The preferred roster is active and ready to support match-day selections."
                ),
            }
        if roster.status == "active":
            return {
                "label": _("Active roster needs attention"),
                "tone": "warning",
                "detail": roster.readiness_feedback
                or _(
                    "The active roster still has readiness issues that should be reviewed before match day."
                ),
            }
        if roster.status == "draft" and roster.ready_for_activation:
            return {
                "label": _("Draft roster ready"),
                "tone": "info",
                "detail": _(
                    "The roster can be activated once the club is ready to lock in the competition squad."
                ),
            }
        if roster.status == "draft":
            return {
                "label": _("Draft roster needs attention"),
                "tone": "warning",
                "detail": roster.readiness_feedback
                or _(
                    "Complete the roster before moving it into active competition use."
                ),
            }
        return {
            "label": _("Roster closed"),
            "tone": "secondary",
            "detail": _(
                "The preferred roster is closed and can only be reviewed, not managed, from the portal."
            ),
        }

    def _portal_get_workspace_entry(self, team, user=None):
        """Handle the portal-specific get workspace entry flow."""
        user = user or self.env.user
        PortalPrivilege = self.env["federation.portal.privilege"]
        tournament, team = self._portal_assert_workspace_access(team, user=user)

        TeamRoster = self.env["federation.team.roster"]
        registration = PortalPrivilege.portal_search(
            self.env["federation.tournament.registration"],
            [
                ("tournament_id", "=", tournament.id),
                ("team_id", "=", team.id),
                ("state", "!=", "cancelled"),
            ],
            order="create_date desc, id desc",
            limit=1,
            user=user,
        )
        participant = PortalPrivilege.portal_search(
            self.env["federation.tournament.participant"],
            [
                ("tournament_id", "=", tournament.id),
                ("team_id", "=", team.id),
            ],
            order="id desc",
            limit=1,
            user=user,
        )
        roster = TeamRoster._portal_get_preferred_roster_for_tournament(
            tournament,
            team,
            user=user,
        )
        upcoming_match_sheets = PortalPrivilege.portal_search(
            self.env["federation.match.sheet"],
            [
                ("match_id.tournament_id", "=", tournament.id),
                ("team_id", "=", team.id),
                ("match_id.state", "in", ("draft", "scheduled", "in_progress")),
                ("match_kickoff", "!=", False),
            ],
            order="match_kickoff asc, id asc",
            user=user,
        )
        result_follow_up_matches = PortalPrivilege.portal_search(
            self.env["federation.match"],
            [
                ("tournament_id", "=", tournament.id),
                "|",
                ("home_team_id", "=", team.id),
                ("away_team_id", "=", team.id),
                ("state", "=", "done"),
                ("result_state", "in", self._portal_workspace_result_follow_up_states),
            ],
            order="date_scheduled desc, id desc",
            user=user,
        )
        result_follow_up_sheets = PortalPrivilege.portal_search(
            self.env["federation.match.sheet"],
            [
                ("match_id", "in", result_follow_up_matches.ids),
                ("team_id", "=", team.id),
            ],
            user=user,
        )
        follow_up_sheet_by_match_id = {
            sheet.match_id.id: sheet for sheet in result_follow_up_sheets
        }
        result_follow_up_rows = [
            {
                "match": match,
                "sheet": follow_up_sheet_by_match_id.get(match.id),
            }
            for match in result_follow_up_matches
        ]

        return {
            "tournament": tournament,
            "team": team,
            "club": team.club_id,
            "tournament_registration": registration,
            "participant": participant,
            "registration_checkpoint": tournament._portal_get_registration_checkpoint(
                registration,
                participant,
            ),
            "roster": roster,
            "roster_checkpoint": tournament._portal_get_roster_checkpoint(roster),
            "upcoming_match_sheets": upcoming_match_sheets,
            "pending_match_day_count": len(
                upcoming_match_sheets.filtered(lambda sheet: sheet.state == "draft")
            ),
            "result_follow_up_matches": result_follow_up_matches,
            "result_follow_up_rows": result_follow_up_rows,
            "result_follow_up_count": len(result_follow_up_rows),
        }

    @api.model
    def _portal_workspace_entry_has_activity(self, entry):
        """Handle the portal-specific workspace entry has activity flow."""
        return bool(
            entry["tournament_registration"]
            or entry["participant"]
            or entry["upcoming_match_sheets"]
            or entry["result_follow_up_matches"]
        )

    @api.model
    def _portal_get_workspace_entry_for_user(self, tournament_id, team_id, user=None):
        """Handle the portal-specific get workspace entry for user flow."""
        user = user or self.env.user
        PortalPrivilege = self.env["federation.portal.privilege"]
        team_domain = self._portal_get_workspace_team_domain(user=user)
        if team_domain == [("id", "=", False)]:
            return False

        team = PortalPrivilege.portal_search(
            self.env["federation.team"],
            team_domain + [("id", "=", team_id)],
            limit=1,
            user=user,
        )
        if not team:
            return False

        tournament = PortalPrivilege.portal_search(
            self,
            self._portal_get_workspace_tournament_domain()
            + [("id", "=", tournament_id)],
            limit=1,
            user=user,
        )
        if not tournament:
            return False

        entry = tournament._portal_get_workspace_entry(team, user=user)
        if not self._portal_workspace_entry_has_activity(entry):
            return False
        return entry

    @api.model
    def _portal_get_workspace_entries(self, user=None):
        """Handle the portal-specific get workspace entries flow."""
        user = user or self.env.user
        PortalPrivilege = self.env["federation.portal.privilege"]
        team_domain = self._portal_get_workspace_team_domain(user=user)
        if team_domain == [("id", "=", False)]:
            return []

        teams = PortalPrivilege.portal_search(
            self.env["federation.team"],
            team_domain,
            user=user,
        )
        if not teams:
            return []

        team_ids = set(teams.ids)
        active_tournaments = PortalPrivilege.portal_search(
            self,
            self._portal_get_workspace_tournament_domain(),
            user=user,
        )
        if not active_tournaments:
            return []

        active_tournament_ids = active_tournaments.ids
        team_by_id = {team.id: team for team in teams}
        tournament_by_id = {
            tournament.id: tournament for tournament in active_tournaments
        }

        pair_keys = set()

        registrations = PortalPrivilege.portal_search(
            self.env["federation.tournament.registration"],
            [
                ("team_id", "in", list(team_ids)),
                ("tournament_id", "in", active_tournament_ids),
                ("state", "!=", "cancelled"),
            ],
            user=user,
        )
        for registration in registrations:
            pair_keys.add((registration.tournament_id.id, registration.team_id.id))

        participants = PortalPrivilege.portal_search(
            self.env["federation.tournament.participant"],
            [
                ("team_id", "in", list(team_ids)),
                ("tournament_id", "in", active_tournament_ids),
            ],
            user=user,
        )
        for participant in participants:
            pair_keys.add((participant.tournament_id.id, participant.team_id.id))

        matches = PortalPrivilege.portal_search(
            self.env["federation.match"],
            [
                ("tournament_id", "in", active_tournament_ids),
                "|",
                ("home_team_id", "in", list(team_ids)),
                ("away_team_id", "in", list(team_ids)),
            ],
            user=user,
        )
        for match in matches:
            if match.home_team_id.id in team_ids:
                pair_keys.add((match.tournament_id.id, match.home_team_id.id))
            if match.away_team_id.id in team_ids:
                pair_keys.add((match.tournament_id.id, match.away_team_id.id))

        state_order = {"in_progress": 0, "open": 1}
        sorted_keys = sorted(
            pair_keys,
            key=lambda item: (
                state_order.get(tournament_by_id[item[0]].state, 99),
                tournament_by_id[item[0]].date_start or fields.Date.today(),
                tournament_by_id[item[0]].id,
                team_by_id[item[1]].display_name,
            ),
        )

        entries = []
        for tournament_id, team_id in sorted_keys:
            entry = tournament_by_id[tournament_id]._portal_get_workspace_entry(
                team_by_id[team_id],
                user=user,
            )
            if self._portal_workspace_entry_has_activity(entry):
                entries.append(entry)
        return entries
