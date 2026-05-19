from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_TOURNAMENT_STATE_LABELS = {
    "draft": "Not ready",
    "open": "Open",
    "in_progress": "Live",
    "closed": "Finished",
    "cancelled": "Cancelled",
}

_TOURNAMENT_STATE_TONES = {
    "draft": "secondary",
    "open": "info",
    "in_progress": "primary",
    "closed": "success",
    "cancelled": "dark",
}

_MATCH_STATE_LABELS = {
    "draft": "Not scheduled",
    "scheduled": "Scheduled",
    "in_progress": "Playing",
    "done": "Finished",
    "cancelled": "Cancelled",
}

_RESULT_STATE_LABELS = {
    "draft": "Not sent",
    "submitted": "Sent for check",
    "verified": "Checked",
    "approved": "Official",
    "contested": "Under review",
    "corrected": "Corrected - resend",
}

_MATCH_STATE_TONES = {
    "draft": "secondary",
    "scheduled": "info",
    "in_progress": "primary",
    "done": "success",
    "cancelled": "dark",
}

_RESULT_STATE_TONES = {
    "draft": "secondary",
    "submitted": "warning",
    "verified": "info",
    "approved": "success",
    "contested": "danger",
    "corrected": "warning",
}

_ACTION_MESSAGES = {
    "save_score": _("Score saved."),
    "schedule": _("Match scheduled."),
    "start": _("Match started."),
    "finish": _("Match marked as finished."),
    "submit": _("Result submitted for checking."),
    "verify": _("Result verified."),
    "approve": _("Result approved and now counts in official standings."),
    "contest": _("Result marked for review."),
    "correct": _("Result corrected."),
    "reset_to_draft": _("Result reset to draft."),
}


class FederationTournamentOperations(models.Model):
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
        is_manager = (
            access_mode == "internal"
            and user.has_group("sports_federation_base.group_federation_manager")
        )
        can_edit_scores = is_manager or (
            access_mode == "internal"
            and (
                user.has_group("sports_federation_result_control.group_result_validator")
                or user.has_group(
                    "sports_federation_result_control.group_result_approver"
                )
            )
        )
        can_verify = (
            access_mode == "internal"
            and user.has_group("sports_federation_result_control.group_result_validator")
        )
        can_approve = (
            access_mode == "portal"
            or (
                access_mode == "internal"
                and user.has_group(
                    "sports_federation_result_control.group_result_approver"
                )
            )
        )
        can_correct = (
            access_mode == "internal"
            and user.has_group("sports_federation_result_control.group_result_approver")
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
        return Match.with_user(user).search(base_domain, order="date_scheduled asc, id asc")

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
    def _operations_format_datetime_parts(self, value):
        """Return stable datetime strings for UI rendering and sorting."""
        if not value:
            return {
                "value": False,
                "date": False,
                "time": False,
                "label": False,
            }
        dt_value = fields.Datetime.to_datetime(value)
        user_dt = fields.Datetime.context_timestamp(self, dt_value)
        return {
            "value": fields.Datetime.to_string(dt_value),
            "date": user_dt.strftime("%Y-%m-%d"),
            "time": user_dt.strftime("%H:%M"),
            "label": user_dt.strftime("%Y-%m-%d %H:%M"),
        }

    @api.model
    def _operations_format_date_range(self, start_date, end_date):
        """Return a short tournament date label."""
        if not start_date and not end_date:
            return False
        if start_date and end_date and start_date != end_date:
            return f"{start_date.isoformat()} - {end_date.isoformat()}"
        return (start_date or end_date).isoformat()

    @api.model
    def _operations_unique_messages(self, messages):
        """Remove duplicate or empty messages while keeping order."""
        seen = set()
        cleaned = []
        for message in messages:
            if not message:
                continue
            if message in seen:
                continue
            seen.add(message)
            cleaned.append(message)
        return cleaned

    @api.model
    def _operations_get_validation_status(self, result_state):
        """Return a compact validation summary."""
        if result_state == "approved":
            return {"key": "valid", "label": _("Official"), "tone": "success"}
        if result_state == "contested":
            return {"key": "issue", "label": _("Under review"), "tone": "danger"}
        if result_state == "verified":
            return {"key": "approval", "label": _("Needs approval"), "tone": "info"}
        if result_state == "submitted":
            return {"key": "validation", "label": _("Needs validation"), "tone": "warning"}
        if result_state == "corrected":
            return {"key": "resubmit", "label": _("Corrected"), "tone": "warning"}
        return {"key": "draft", "label": _("Not sent"), "tone": "secondary"}

    @api.model
    def _operations_get_match_actions(self, match, capabilities):
        """Return the action set for a single match."""
        actions = []
        has_score_entry = bool(
            capabilities["can_edit_scores"] and match.result_state != "approved"
        )
        if capabilities["can_manage_match_state"] and match.state == "draft":
            actions.append({"key": "schedule", "label": _("Schedule match"), "tone": "secondary"})
        if capabilities["can_manage_match_state"] and match.state == "scheduled":
            actions.append({"key": "start", "label": _("Start match"), "tone": "primary"})
        if capabilities["can_manage_match_state"] and match.state == "in_progress":
            actions.append({"key": "finish", "label": _("Mark finished"), "tone": "primary"})
        if (
            capabilities["can_submit_result"]
            and match.state == "done"
            and match.result_state in ("draft", "corrected")
        ):
            actions.append({"key": "submit", "label": _("Submit result"), "tone": "primary"})
        if capabilities["can_verify_result"] and match.result_state == "submitted":
            actions.append({"key": "verify", "label": _("Validate"), "tone": "warning"})
        if capabilities["can_approve_result"] and match.result_state == "verified":
            actions.append({"key": "approve", "label": _("Approve"), "tone": "success"})
        if has_score_entry:
            actions.append(
                {
                    "key": "save_score",
                    "label": _("Edit result")
                    if match.state in ("in_progress", "done")
                    else _("Enter result"),
                    "tone": "secondary",
                }
            )
        if (
            capabilities["can_contest_result"]
            and match.result_state in ("submitted", "verified", "approved")
        ):
            actions.append({"key": "contest", "label": _("Contest"), "tone": "danger"})
        if capabilities["can_correct_result"] and match.result_state in ("contested", "approved"):
            actions.append({"key": "correct", "label": _("Correct result"), "tone": "warning"})
        if capabilities["can_reset_result"] and match.result_state != "draft":
            actions.append({"key": "reset_to_draft", "label": _("Reset to draft"), "tone": "secondary"})
        primary_action = actions[0] if actions else {"key": "view", "label": _("View"), "tone": "secondary"}
        return {
            "primary_action": primary_action,
            "secondary_actions": actions[1:],
        }

    def _operations_serialize_tournament(self):
        """Return tournament metadata for the operations board."""
        self.ensure_one()
        tournament_venue = False
        if "venue_id" in self._fields and self.venue_id:
            tournament_venue = self.venue_id.name
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "state_label": _TOURNAMENT_STATE_LABELS.get(self.state, self.state),
            "state_tone": _TOURNAMENT_STATE_TONES.get(self.state, "secondary"),
            "date_start": self.date_start.isoformat() if self.date_start else False,
            "date_end": self.date_end.isoformat() if self.date_end else False,
            "date_label": self._operations_format_date_range(
                self.date_start,
                self.date_end,
            ),
            "location": self.location or False,
            "venue_name": tournament_venue,
        }

    def _operations_serialize_match(self, match, now_dt=False, user=None):
        """Return the frontend payload for one match."""
        self.ensure_one()
        user = user or self.env.user
        capabilities = self._operations_get_user_capabilities(user=user)
        schedule = self._operations_format_datetime_parts(match.date_scheduled)
        now_dt = now_dt or fields.Datetime.now()
        scheduled_dt = (
            fields.Datetime.to_datetime(match.date_scheduled)
            if match.date_scheduled
            else False
        )
        is_overdue = bool(
            scheduled_dt
            and match.state in ("draft", "scheduled")
            and scheduled_dt < now_dt
        )
        is_now_playing = match.state == "in_progress"
        is_completed = match.state == "done"
        is_missing_result = is_completed and match.result_state in ("draft", "corrected")
        needs_validation = match.result_state in ("submitted", "verified")
        has_validation_issue = match.result_state == "contested"
        Venue = self.env.get("federation.venue")
        PlayingArea = self.env.get("federation.playing.area")
        venue = match.venue_id if "venue_id" in match._fields else (Venue.browse([]) if Venue else False)
        playing_area = (
            match.playing_area_id
            if "playing_area_id" in match._fields
            else (PlayingArea.browse([]) if PlayingArea else False)
        )
        court_name = playing_area.name if playing_area else _("Unassigned court")
        venue_name = venue.name if venue else False
        referee_assignments = (
            match.referee_assignment_ids
            if "referee_assignment_ids" in match._fields
            else self.env["federation.match.referee"].browse([])
        )
        sorted_assignments = referee_assignments.sorted(
            key=lambda assignment: (
                assignment.state not in ("confirmed", "done"),
                assignment.role != "head",
                assignment.id,
            )
        )
        primary_referee = sorted_assignments[:1]
        officiating_issues = []
        if "official_readiness_issues" in match._fields and match.official_readiness_issues:
            officiating_issues = [
                line.strip()
                for line in match.official_readiness_issues.splitlines()
                if line.strip()
            ]
        attention_items = []
        if "venue_id" in match._fields and not match.venue_id:
            attention_items.append(_("Venue missing."))
        if "playing_area_id" in match._fields and not match.playing_area_id:
            attention_items.append(_("Court or playing area is missing."))
        if is_overdue:
            attention_items.append(_("Scheduled kickoff has already passed."))
        if is_missing_result:
            attention_items.append(_("Result still needs to be submitted."))
        if match.result_state == "submitted":
            attention_items.append(_("Result is waiting for validation."))
        if match.result_state == "verified":
            attention_items.append(_("Result is waiting for approval."))
        if match.result_state == "contested":
            attention_items.append(_("Result is under review."))
        attention_items.extend(officiating_issues)
        attention_items = self._operations_unique_messages(attention_items)
        has_court_issue = bool(
            ("playing_area_id" in match._fields and not match.playing_area_id)
            or is_overdue
        )
        has_score = bool(
            match.state in ("in_progress", "done")
            or match.result_state != "draft"
            or match.home_score
            or match.away_score
        )
        validation_status = self._operations_get_validation_status(match.result_state)
        actions = self._operations_get_match_actions(match, capabilities)
        latest_audit = match.result_audit_ids[:1]
        return {
            "id": match.id,
            "name": match.name,
            "scheduled_datetime": schedule["value"],
            "scheduled_date_label": schedule["date"],
            "scheduled_time_label": schedule["time"],
            "scheduled_label": schedule["label"],
            "state": match.state,
            "state_label": _MATCH_STATE_LABELS.get(match.state, match.state),
            "state_tone": _MATCH_STATE_TONES.get(match.state, "secondary"),
            "result_state": match.result_state,
            "result_state_label": _RESULT_STATE_LABELS.get(
                match.result_state,
                match.result_state,
            ),
            "result_state_tone": _RESULT_STATE_TONES.get(match.result_state, "secondary"),
            "validation_status": validation_status,
            "home_team_name": match.home_team_id.display_name if match.home_team_id else _("TBD"),
            "away_team_name": match.away_team_id.display_name if match.away_team_id else _("TBD"),
            "home_score": match.home_score,
            "away_score": match.away_score,
            "has_score": has_score,
            "stage_name": match.stage_id.name if match.stage_id else False,
            "group_name": match.group_id.name if match.group_id else False,
            "round_name": match.round_id.name if match.round_id else False,
            "venue_name": venue_name,
            "court_id": playing_area.id if playing_area else False,
            "court_name": court_name,
            "referee_name": primary_referee.referee_id.name if primary_referee else False,
            "referee_summary": ", ".join(
                assignment.referee_id.name
                for assignment in sorted_assignments[:3]
                if assignment.referee_id
            )
            if sorted_assignments
            else False,
            "referee_assignments": [
                {
                    "id": assignment.id,
                    "name": assignment.referee_id.name,
                    "role": assignment.role,
                    "role_label": dict(
                        assignment._fields["role"].selection
                    ).get(assignment.role, assignment.role),
                    "state": assignment.state,
                    "state_label": dict(
                        assignment._fields["state"].selection
                    ).get(assignment.state, assignment.state),
                }
                for assignment in sorted_assignments
            ],
            "officials_ready": (
                match.is_officially_ready
                if "is_officially_ready" in match._fields
                else False
            ),
            "missing_referees_count": (
                match.missing_referees_count
                if "missing_referees_count" in match._fields
                else 0
            ),
            "overdue_referee_confirmation_count": (
                match.overdue_referee_confirmation_count
                if "overdue_referee_confirmation_count" in match._fields
                else 0
            ),
            "official_readiness_issues": officiating_issues,
            "result_submitted_by_name": (
                match.result_submitted_by_id.name if match.result_submitted_by_id else False
            ),
            "result_submitted_on": (
                self._operations_format_datetime_parts(match.result_submitted_on)["label"]
                if match.result_submitted_on
                else False
            ),
            "result_verified_by_name": (
                match.result_verified_by_id.name if match.result_verified_by_id else False
            ),
            "result_verified_on": (
                self._operations_format_datetime_parts(match.result_verified_on)["label"]
                if match.result_verified_on
                else False
            ),
            "result_approved_by_name": (
                match.result_approved_by_id.name if match.result_approved_by_id else False
            ),
            "result_approved_on": (
                self._operations_format_datetime_parts(match.result_approved_on)["label"]
                if match.result_approved_on
                else False
            ),
            "result_contest_reason": match.result_contest_reason or False,
            "result_correction_reason": match.result_correction_reason or False,
            "latest_audit_description": latest_audit.description if latest_audit else False,
            "latest_audit_reason": latest_audit.reason if latest_audit else False,
            "timeline_bucket": (
                "current"
                if is_now_playing
                else "completed"
                if is_completed
                else "overdue"
                if is_overdue
                else "upcoming"
            ),
            "is_now_playing": is_now_playing,
            "is_completed": is_completed,
            "is_missing_result": is_missing_result,
            "needs_validation": needs_validation,
            "has_validation_issue": has_validation_issue,
            "has_court_issue": has_court_issue,
            "needs_attention": bool(attention_items),
            "attention_items": attention_items,
            "capabilities": capabilities,
            "primary_action": actions["primary_action"],
            "secondary_actions": actions["secondary_actions"],
        }

    @api.model
    def _operations_build_summary(self, serialized_matches):
        """Return aggregate summary counters."""
        actionable_matches = [match for match in serialized_matches if match["state"] != "cancelled"]
        return {
            "match_count": len(serialized_matches),
            "completed_count": sum(1 for match in actionable_matches if match["is_completed"]),
            "missing_result_count": sum(
                1 for match in actionable_matches if match["is_missing_result"]
            ),
            "validation_issue_count": sum(
                1 for match in actionable_matches if match["has_validation_issue"]
            ),
            "now_playing_count": sum(
                1 for match in actionable_matches if match["is_now_playing"]
            ),
            "next_match_count": sum(
                1
                for match in actionable_matches
                if match["timeline_bucket"] in ("upcoming", "overdue")
            ),
            "needs_validation_count": sum(
                1 for match in actionable_matches if match["needs_validation"]
            ),
            "court_issue_count": sum(
                1 for match in actionable_matches if match["has_court_issue"]
            ),
        }

    @api.model
    def _operations_build_filter_options(self, serialized_matches):
        """Return filter option lists derived from the serialized data."""
        courts = {}
        referees = {}
        for match in serialized_matches:
            court_key = str(match["court_id"] or "unassigned")
            courts[court_key] = {
                "value": court_key,
                "label": match["court_name"],
            }
            if match["referee_name"]:
                referees[match["referee_name"]] = {
                    "value": match["referee_name"],
                    "label": match["referee_name"],
                }
        return {
            "courts": sorted(courts.values(), key=lambda item: item["label"]),
            "referees": sorted(referees.values(), key=lambda item: item["label"]),
            "match_states": [
                {"value": value, "label": label}
                for value, label in _MATCH_STATE_LABELS.items()
            ],
            "result_states": [
                {"value": value, "label": label}
                for value, label in _RESULT_STATE_LABELS.items()
            ],
        }

    @api.model
    def _operations_get_default_match_id(self, serialized_matches):
        """Return the first high-value match to focus when the board opens."""
        for predicate in (
            lambda match: match["is_now_playing"],
            lambda match: match["is_missing_result"],
            lambda match: match["needs_validation"],
            lambda match: match["needs_attention"],
            lambda match: match["timeline_bucket"] == "upcoming",
        ):
            for match in serialized_matches:
                if predicate(match):
                    return match["id"]
        return serialized_matches[0]["id"] if serialized_matches else False

    def _operations_get_payload(self, user=None):
        """Return the full operations board payload."""
        self.ensure_one()
        user = user or self.env.user
        now_dt = fields.Datetime.now()
        serialized_matches = [
            self._operations_serialize_match(match, now_dt=now_dt, user=user)
            for match in self._operations_get_matches_for_user(user=user)
        ]
        generated_at = self._operations_format_datetime_parts(now_dt)
        return {
            "tournament": self._operations_serialize_tournament(),
            "summary": self._operations_build_summary(serialized_matches),
            "filters": self._operations_build_filter_options(serialized_matches),
            "matches": serialized_matches,
            "default_match_id": self._operations_get_default_match_id(serialized_matches),
            "generated_at": generated_at["label"],
            "generated_at_value": generated_at["value"],
        }

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
        PortalPrivilege = self.env["federation.portal.privilege"]

        def portal_write(write_values):
            return PortalPrivilege.portal_write(match, write_values, user=user)

        def portal_call(method_name):
            return PortalPrivilege.portal_call(match, method_name, user=user)

        def internal_write(write_values):
            return match.with_user(user).write(write_values)

        def internal_call(method_name):
            return getattr(match.with_user(user), method_name)()

        writer = portal_write if access_mode == "portal" else internal_write
        caller = portal_call if access_mode == "portal" else internal_call
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
            raise ValidationError(_("This action is not available from the operations board."))
        return _ACTION_MESSAGES.get(action_key, _("Update saved."))
