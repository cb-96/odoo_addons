from odoo import _, api, models
from odoo.exceptions import ValidationError

from .tournament_operations_access import TournamentOperationsAccessMixin
from .tournament_operations_board import TournamentOperationsBoardMixin

_ACTION_MESSAGES = {
    "save_score": "Score saved.",
    "schedule": "Match scheduled.",
    "start": "Match started.",
    "finish": "Match marked as finished.",
    "submit": "Result submitted for checking.",
    "verify": "Result verified.",
    "approve": "Result approved and now counts in official standings.",
    "contest": "Result marked for review.",
    "correct": "Result corrected.",
    "reset_to_draft": "Result reset to draft.",
}


class FederationTournamentOperations(
    TournamentOperationsBoardMixin,
    TournamentOperationsAccessMixin,
    models.Model,
):
    _inherit = "federation.tournament"

    def action_open_operations_portal(self):
        """Open the tournament operations board in the website/portal shell."""
        self.ensure_one()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return {
            "type": "ir.actions.act_url",
            "url": f"{base_url}/sports/tournament/{self.id}/operations",
            "target": "new",
        }

    @api.model
    def _operations_is_portal_mode(self, user=None):
        """Return whether the operations page should use the portal access path."""
        user = user or self.env.user
        return bool(
            user.share
            and user.has_group("sports_federation_portal.group_federation_portal_club")
        )

    @api.model
    def _operations_get_access_mode(self, user=None):
        """Return the current operations access mode."""
        return "portal" if self._operations_is_portal_mode(user=user) else "internal"

    @api.model
    def _operations_get_user_capabilities(self, user=None, access_mode=False):
        """Return page capabilities for the supplied user."""
        user = user or self.env.user
        access_mode = access_mode or self._operations_get_access_mode(user=user)
        is_manager = access_mode == "internal" and user.has_group(
            "sports_federation_base.group_federation_manager"
        )
        can_edit_scores = is_manager or (
            access_mode == "internal"
            and (
                user.has_group(
                    "sports_federation_result_control.group_result_validator"
                )
                or user.has_group(
                    "sports_federation_result_control.group_result_approver"
                )
            )
        )
        can_verify = access_mode == "internal" and user.has_group(
            "sports_federation_result_control.group_result_validator"
        )
        can_approve = access_mode == "portal" or (
            access_mode == "internal"
            and user.has_group("sports_federation_result_control.group_result_approver")
        )
        can_correct = access_mode == "internal" and user.has_group(
            "sports_federation_result_control.group_result_approver"
        )
        return {
            "access_mode": access_mode,
            "is_manager": is_manager,
            "can_manage_match_state": is_manager,
            "can_edit_scores": can_edit_scores,
            "can_submit_result": can_edit_scores,
            "can_verify_result": can_verify,
            "can_approve_result": can_approve,
            "can_contest_result": can_approve or can_edit_scores,
            "can_correct_result": can_correct,
            "can_reset_result": can_correct,
        }

    @api.model
    def _operations_get_portal_match_scope_domain(self, user=None):
        """Return the domain that mirrors portal match visibility."""
        user = user or self.env.user
        team_ids = user.portal_team_scope_ids.ids
        club_ids = user.portal_club_scope_ids.ids
        if team_ids and club_ids:
            return [
                "|",
                "|",
                ("home_team_id", "in", team_ids),
                ("away_team_id", "in", team_ids),
                "|",
                ("home_team_id.club_id", "in", club_ids),
                ("away_team_id.club_id", "in", club_ids),
            ]
        if team_ids:
            return [
                "|",
                ("home_team_id", "in", team_ids),
                ("away_team_id", "in", team_ids),
            ]
        if club_ids:
            return [
                "|",
                ("home_team_id.club_id", "in", club_ids),
                ("away_team_id.club_id", "in", club_ids),
            ]
        return [("id", "=", False)]

    @api.model
    def _operations_has_portal_tournament_scope(self, tournament, user=None):
        """Return whether the portal user has any tournament-scoped operational record."""
        user = user or self.env.user
        team_domain = self._portal_get_workspace_team_domain(user=user)
        if team_domain == [("id", "=", False)]:
            return False
        PortalPrivilege = self.env["federation.portal.privilege"]
        teams = PortalPrivilege.portal_search(
            self.env["federation.team"],
            team_domain,
            user=user,
        )
        if not teams:
            return False

        team_ids = teams.ids
        if PortalPrivilege.portal_search_count(
            self.env["federation.tournament.registration"],
            [
                ("tournament_id", "=", tournament.id),
                ("team_id", "in", team_ids),
                ("state", "!=", "cancelled"),
            ],
            user=user,
        ):
            return True
        if PortalPrivilege.portal_search_count(
            self.env["federation.tournament.participant"],
            [
                ("tournament_id", "=", tournament.id),
                ("team_id", "in", team_ids),
            ],
            user=user,
        ):
            return True
        return bool(
            PortalPrivilege.portal_search_count(
                self.env["federation.match"],
                [("tournament_id", "=", tournament.id)]
                + self._operations_get_portal_match_scope_domain(user=user),
                user=user,
            )
        )

    @api.model
    def _operations_get_tournament_for_user(self, tournament_id, user=None):
        """Resolve one tournament inside the permitted access boundary."""
        user = user or self.env.user
        if self._operations_is_portal_mode(user=user):
            team_domain = self._portal_get_workspace_team_domain(user=user)
            if team_domain == [("id", "=", False)]:
                return self.browse([])
            tournament = self.env["federation.portal.privilege"].portal_search(
                self,
                self._portal_get_workspace_tournament_domain()
                + [("id", "=", tournament_id)],
                user=user,
                limit=1,
            )
            if tournament and self._operations_has_portal_tournament_scope(
                tournament,
                user=user,
            ):
                return tournament
            return self.browse([])
        return self.with_user(user).search([("id", "=", tournament_id)], limit=1)

    def _operations_get_matches_for_user(self, user=None):
        """Return matches visible in the operations board for the supplied user."""
        self.ensure_one()
        user = user or self.env.user
        Match = self.env["federation.match"]
        base_domain = [("tournament_id", "=", self.id)]
        if self._operations_is_portal_mode(user=user):
            scope_domain = self._operations_get_portal_match_scope_domain(user=user)
            if scope_domain == [("id", "=", False)]:
                return Match.browse([])
            return self.env["federation.portal.privilege"].portal_search(
                Match,
                base_domain + scope_domain,
                user=user,
                order="date_scheduled asc, id asc",
            )
        return Match.with_user(user).search(
            base_domain, order="date_scheduled asc, id asc"
        )

    def _operations_get_match_for_user(self, match_id, user=None):
        """Resolve one match inside the board access boundary."""
        self.ensure_one()
        user = user or self.env.user
        Match = self.env["federation.match"]
        base_domain = [("tournament_id", "=", self.id), ("id", "=", match_id)]
        if self._operations_is_portal_mode(user=user):
            scope_domain = self._operations_get_portal_match_scope_domain(user=user)
            if scope_domain == [("id", "=", False)]:
                return Match.browse([])
            return self.env["federation.portal.privilege"].portal_search(
                Match,
                base_domain + scope_domain,
                user=user,
                limit=1,
            )
        return Match.with_user(user).search(base_domain, limit=1)

    @api.model
    def _operations_parse_score_value(self, raw_value, label):
        """Parse one score value from a JSON payload."""
        if raw_value in (None, ""):
            return None
        try:
            parsed_value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(_("%s must be a whole number.") % label) from exc
        if parsed_value < 0:
            raise ValidationError(_("%s cannot be negative.") % label)
        return parsed_value

    def _operations_prepare_score_values(self, values, match=False, required=False):
        """Prepare score values for write operations."""
        self.ensure_one()
        prepared_values = {}
        source_values = values or {}
        for field_name, label in (
            ("home_score", _("Home score")),
            ("away_score", _("Away score")),
        ):
            raw_value = source_values.get(
                field_name,
                match[field_name] if match else None,
            )
            parsed_value = self._operations_parse_score_value(raw_value, label)
            if parsed_value is None:
                continue
            prepared_values[field_name] = parsed_value
        if required and set(prepared_values) != {"home_score", "away_score"}:
            raise ValidationError(_("Enter both scores before continuing."))
        return prepared_values

    def _operations_apply_action(self, match, action_key, values=None, user=None):
        """Apply one safe operations-board action to the supplied match."""
        self.ensure_one()
        user = user or self.env.user
        values = dict(values or {})
        access_mode = self._operations_get_access_mode(user=user)
        capabilities = self._operations_get_user_capabilities(
            user=user,
            access_mode=access_mode,
        )
        portal_scope_domain = self._operations_get_portal_match_scope_domain(user=user)
        writer, caller = self._operations_get_action_handlers(
            match,
            access_mode,
            portal_scope_domain,
            user,
        )
        action_key = action_key or "save_score"

        if action_key == "save_score":
            if not capabilities["can_edit_scores"]:
                raise ValidationError(
                    _("You do not have permission to update scores from this page.")
                )
            writer(
                self._operations_prepare_score_values(
                    values,
                    match=match,
                    required=True,
                )
            )
        elif action_key == "schedule":
            if not capabilities["can_manage_match_state"]:
                raise ValidationError(
                    _("You do not have permission to schedule matches from this page.")
                )
            if match.state != "draft":
                raise ValidationError(_("Only draft matches can be scheduled."))
            caller("action_schedule")
        elif action_key == "start":
            if not capabilities["can_manage_match_state"]:
                raise ValidationError(
                    _("You do not have permission to start matches from this page.")
                )
            if match.state != "scheduled":
                raise ValidationError(_("Only scheduled matches can be started."))
            caller("action_start")
        elif action_key == "finish":
            if not capabilities["can_manage_match_state"]:
                raise ValidationError(
                    _("You do not have permission to finish matches from this page.")
                )
            if match.state != "in_progress":
                raise ValidationError(_("Only matches in progress can be finished."))
            if capabilities["can_edit_scores"]:
                writer(
                    self._operations_prepare_score_values(
                        values,
                        match=match,
                        required=True,
                    )
                )
            caller("action_done")
        elif action_key == "submit":
            if not capabilities["can_submit_result"]:
                raise ValidationError(
                    _("You do not have permission to submit results from this page.")
                )
            if match.state != "done":
                raise ValidationError(
                    _("Mark the match as finished before submitting the result.")
                )
            writer(
                self._operations_prepare_score_values(
                    values,
                    match=match,
                    required=True,
                )
            )
            caller("action_submit_result")
        elif action_key == "verify":
            if not capabilities["can_verify_result"]:
                raise ValidationError(
                    _("You do not have permission to validate results from this page.")
                )
            caller("action_verify_result")
        elif action_key == "approve":
            if not capabilities["can_approve_result"]:
                raise ValidationError(
                    _("You do not have permission to approve results from this page.")
                )
            caller("action_approve_result")
        elif action_key == "contest":
            if not capabilities["can_contest_result"]:
                raise ValidationError(
                    _("You do not have permission to contest results from this page.")
                )
            contest_reason = (values.get("result_contest_reason") or "").strip()
            if contest_reason:
                writer({"result_contest_reason": contest_reason})
            caller("action_contest_result")
        elif action_key == "correct":
            if not capabilities["can_correct_result"]:
                raise ValidationError(
                    _("You do not have permission to correct results from this page.")
                )
            correction_reason = (values.get("result_correction_reason") or "").strip()
            if correction_reason:
                writer({"result_correction_reason": correction_reason})
            caller("action_correct_result")
        elif action_key == "reset_to_draft":
            if not capabilities["can_reset_result"]:
                raise ValidationError(
                    _("You do not have permission to reset results from this page.")
                )
            caller("action_reset_result_to_draft")
        else:
            raise ValidationError(
                _("This action is not available from the operations board.")
            )
        return _(_ACTION_MESSAGES.get(action_key, "Update saved."))
