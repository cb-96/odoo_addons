from odoo import _, api, fields

from .tournament_operations_formatting import (
    _MATCH_STATE_LABELS,
    _MATCH_STATE_TONES,
    _RESULT_STATE_LABELS,
    _RESULT_STATE_TONES,
    _TOURNAMENT_STATE_LABELS,
    _TOURNAMENT_STATE_TONES,
    TournamentOperationsFormattingMixin,
)


class TournamentOperationsBoardMixin(TournamentOperationsFormattingMixin):
    @api.model
    def _operations_get_match_actions(self, match, capabilities):
        """Return the action set for a single match."""
        actions = []
        has_score_entry = bool(
            capabilities["can_edit_scores"] and match.result_state != "approved"
        )
        if capabilities["can_manage_match_state"] and match.state == "draft":
            actions.append(
                {"key": "schedule", "label": _("Schedule match"), "tone": "secondary"}
            )
        if capabilities["can_manage_match_state"] and match.state == "scheduled":
            actions.append(
                {"key": "start", "label": _("Start match"), "tone": "primary"}
            )
        if capabilities["can_manage_match_state"] and match.state == "in_progress":
            actions.append(
                {"key": "finish", "label": _("Mark finished"), "tone": "primary"}
            )
        if (
            capabilities["can_submit_result"]
            and match.state == "done"
            and match.result_state in ("draft", "corrected")
        ):
            actions.append(
                {"key": "submit", "label": _("Send for check"), "tone": "primary"}
            )
        if capabilities["can_verify_result"] and match.result_state == "submitted":
            actions.append(
                {"key": "verify", "label": _("Check result"), "tone": "warning"}
            )
        if capabilities["can_approve_result"] and match.result_state == "verified":
            actions.append(
                {"key": "approve", "label": _("Make official"), "tone": "success"}
            )
        if has_score_entry:
            actions.append(
                {
                    "key": "save_score",
                    "label": (
                        _("Save score")
                        if match.state in ("in_progress", "done")
                        else _("Enter score")
                    ),
                    "tone": "secondary",
                }
            )
        if capabilities["can_contest_result"] and match.result_state in (
            "submitted",
            "verified",
            "approved",
        ):
            actions.append(
                {"key": "contest", "label": _("Send to review"), "tone": "danger"}
            )
        if capabilities["can_correct_result"] and match.result_state in (
            "contested",
            "approved",
        ):
            actions.append(
                {"key": "correct", "label": _("Update result"), "tone": "warning"}
            )
        if capabilities["can_reset_result"] and match.result_state != "draft":
            actions.append(
                {
                    "key": "reset_to_draft",
                    "label": _("Reset to draft"),
                    "tone": "secondary",
                }
            )
        primary_action = (
            actions[0]
            if actions
            else {"key": "view", "label": _("View"), "tone": "secondary"}
        )
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
        schedule_status = self._operations_get_schedule_status(
            match,
            scheduled_dt,
            now_dt,
        )
        is_overdue = bool(
            scheduled_dt
            and match.state in ("draft", "scheduled")
            and scheduled_dt < now_dt
        )
        is_now_playing = match.state == "in_progress"
        is_completed = match.state == "done"
        is_missing_result = is_completed and match.result_state in (
            "draft",
            "corrected",
        )
        needs_validation = match.result_state in ("submitted", "verified")
        has_validation_issue = match.result_state == "contested"
        venue_model = self.env.get("federation.venue")
        playing_area_model = self.env.get("federation.playing.area")
        venue = (
            match.venue_id
            if "venue_id" in match._fields
            else (venue_model.browse([]) if venue_model else False)
        )
        playing_area = (
            match.playing_area_id
            if "playing_area_id" in match._fields
            else (playing_area_model.browse([]) if playing_area_model else False)
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
        if (
            "official_readiness_issues" in match._fields
            and match.official_readiness_issues
        ):
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
        match_sheet_status = self._operations_get_match_sheet_status(match)
        actions = self._operations_get_match_actions(match, capabilities)
        next_step = self._operations_get_next_step(
            match,
            actions,
            schedule_status,
            match_sheet_status,
        )
        latest_audit = match.result_audit_ids[:1]
        if match.state in ("draft", "scheduled"):
            if match_sheet_status["key"] in ("missing", "draft", "submitted"):
                attention_items.append(match_sheet_status["label"])
        attention_items = self._operations_unique_messages(attention_items)
        is_blocked = bool(
            next_step["key"]
            in (
                "assign_venue",
                "assign_court",
                "collect_team_sheet",
                "approve_team_sheet",
                "fix_officiating",
                "confirm_officiating",
            )
        )
        return {
            "id": match.id,
            "name": match.name,
            "scheduled_datetime": schedule["value"],
            "scheduled_date_label": schedule["date"],
            "scheduled_time_label": schedule["time"],
            "scheduled_label": schedule["label"],
            "schedule_status": schedule_status,
            "state": match.state,
            "state_label": _MATCH_STATE_LABELS.get(match.state, match.state),
            "state_tone": _MATCH_STATE_TONES.get(match.state, "secondary"),
            "result_state": match.result_state,
            "result_state_label": _RESULT_STATE_LABELS.get(
                match.result_state,
                match.result_state,
            ),
            "result_state_tone": _RESULT_STATE_TONES.get(
                match.result_state, "secondary"
            ),
            "validation_status": validation_status,
            "home_team_name": (
                match.home_team_id.display_name if match.home_team_id else _("TBD")
            ),
            "away_team_name": (
                match.away_team_id.display_name if match.away_team_id else _("TBD")
            ),
            "home_score": match.home_score,
            "away_score": match.away_score,
            "has_score": has_score,
            "stage_name": match.stage_id.name if match.stage_id else False,
            "group_name": match.group_id.name if match.group_id else False,
            "round_name": match.round_id.name if match.round_id else False,
            "venue_name": venue_name,
            "court_id": playing_area.id if playing_area else False,
            "court_name": court_name,
            "referee_name": (
                primary_referee.referee_id.name if primary_referee else False
            ),
            "referee_summary": (
                ", ".join(
                    assignment.referee_id.name
                    for assignment in sorted_assignments[:3]
                    if assignment.referee_id
                )
                if sorted_assignments
                else False
            ),
            "referee_assignments": [
                {
                    "id": assignment.id,
                    "name": assignment.referee_id.name,
                    "role": assignment.role,
                    "role_label": dict(assignment._fields["role"].selection).get(
                        assignment.role, assignment.role
                    ),
                    "state": assignment.state,
                    "state_label": dict(assignment._fields["state"].selection).get(
                        assignment.state, assignment.state
                    ),
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
                match.result_submitted_by_id.name
                if match.result_submitted_by_id
                else False
            ),
            "result_submitted_on": (
                self._operations_format_datetime_parts(match.result_submitted_on)[
                    "label"
                ]
                if match.result_submitted_on
                else False
            ),
            "result_verified_by_name": (
                match.result_verified_by_id.name
                if match.result_verified_by_id
                else False
            ),
            "result_verified_on": (
                self._operations_format_datetime_parts(match.result_verified_on)[
                    "label"
                ]
                if match.result_verified_on
                else False
            ),
            "result_approved_by_name": (
                match.result_approved_by_id.name
                if match.result_approved_by_id
                else False
            ),
            "result_approved_on": (
                self._operations_format_datetime_parts(match.result_approved_on)[
                    "label"
                ]
                if match.result_approved_on
                else False
            ),
            "result_contest_reason": match.result_contest_reason or False,
            "result_correction_reason": match.result_correction_reason or False,
            "latest_audit_description": (
                latest_audit.description if latest_audit else False
            ),
            "latest_audit_reason": latest_audit.reason if latest_audit else False,
            "timeline_bucket": (
                "current"
                if is_now_playing
                else (
                    "completed"
                    if is_completed
                    else "overdue" if is_overdue else "upcoming"
                )
            ),
            "is_now_playing": is_now_playing,
            "is_completed": is_completed,
            "is_missing_result": is_missing_result,
            "needs_validation": needs_validation,
            "has_validation_issue": has_validation_issue,
            "has_court_issue": has_court_issue,
            "is_blocked": is_blocked,
            "needs_attention": bool(attention_items),
            "attention_items": attention_items,
            "match_sheet_status": match_sheet_status,
            "next_step": next_step,
            "capabilities": capabilities,
            "primary_action": actions["primary_action"],
            "secondary_actions": actions["secondary_actions"],
        }

    @api.model
    def _operations_build_summary(self, serialized_matches):
        """Return aggregate summary counters."""
        actionable_matches = [
            match for match in serialized_matches if match["state"] != "cancelled"
        ]
        return {
            "match_count": len(serialized_matches),
            "completed_count": sum(
                1 for match in actionable_matches if match["is_completed"]
            ),
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
            "blocked_match_count": sum(
                1 for match in actionable_matches if match["is_blocked"]
            ),
            "delayed_match_count": sum(
                1
                for match in actionable_matches
                if match["schedule_status"]["is_overdue"]
            ),
        }

    @api.model
    def _operations_build_action_queue(self, serialized_matches):
        """Return a ranked list of the most useful next actions."""
        queue_matches = [
            match
            for match in serialized_matches
            if match["state"] != "cancelled"
            and (
                match["is_now_playing"]
                or match["needs_attention"]
                or match["primary_action"]["key"] != "view"
            )
        ]
        queue_matches.sort(
            key=lambda match: (
                match["next_step"]["urgency_weight"],
                match["scheduled_datetime"] or "",
                match["court_name"],
                match["id"],
            )
        )
        return [
            {
                "match_id": match["id"],
                "title": match["next_step"]["label"],
                "tone": match["next_step"]["tone"],
                "owner_label": match["next_step"]["owner_label"],
                "teams_label": _("%(home)s vs %(away)s")
                % {
                    "home": match["home_team_name"],
                    "away": match["away_team_name"],
                },
                "court_name": match["court_name"],
                "schedule_label": match["schedule_status"]["short_label"],
                "action_label": match["primary_action"]["label"],
                "summary": (
                    match["attention_items"][0]
                    if match["attention_items"]
                    else match["validation_status"]["label"]
                ),
            }
            for match in queue_matches[:8]
        ]

    @api.model
    def _operations_build_court_summaries(self, serialized_matches):
        """Return one operational summary card per court."""
        grouped = {}
        for match in serialized_matches:
            court_key = str(match["court_id"] or "unassigned")
            summary = grouped.setdefault(
                court_key,
                {
                    "court_id": match["court_id"],
                    "court_key": court_key,
                    "court_name": match["court_name"],
                    "venue_name": match["venue_name"],
                    "live_count": 0,
                    "delayed_count": 0,
                    "blocked_count": 0,
                    "missing_result_count": 0,
                    "needs_validation_count": 0,
                    "next_match_label": False,
                    "status": {
                        "key": "clear",
                        "label": _("Clear"),
                        "tone": "success",
                    },
                },
            )
            summary["live_count"] += 1 if match["is_now_playing"] else 0
            summary["delayed_count"] += (
                1 if match["schedule_status"]["is_overdue"] else 0
            )
            summary["blocked_count"] += 1 if match["is_blocked"] else 0
            summary["missing_result_count"] += 1 if match["is_missing_result"] else 0
            summary["needs_validation_count"] += 1 if match["needs_validation"] else 0
            if not summary["next_match_label"] and match["timeline_bucket"] in (
                "upcoming",
                "overdue",
            ):
                summary["next_match_label"] = (
                    match["scheduled_time_label"] or match["scheduled_label"]
                )

        court_summaries = []
        for summary in grouped.values():
            if summary["blocked_count"]:
                summary["status"] = {
                    "key": "blocked",
                    "label": _("Blocked"),
                    "tone": "danger",
                }
            elif summary["delayed_count"]:
                summary["status"] = {
                    "key": "delayed",
                    "label": _("Delayed"),
                    "tone": "warning",
                }
            elif summary["live_count"]:
                summary["status"] = {
                    "key": "live",
                    "label": _("Live"),
                    "tone": "primary",
                }
            elif summary["missing_result_count"]:
                summary["status"] = {
                    "key": "results",
                    "label": _("Result follow-up"),
                    "tone": "warning",
                }
            court_summaries.append(summary)

        court_summaries.sort(
            key=lambda summary: (
                {"blocked": 0, "delayed": 1, "live": 2, "results": 3, "clear": 4}.get(
                    summary["status"]["key"],
                    9,
                ),
                summary["court_name"],
            )
        )
        return court_summaries

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
    def _operations_get_default_match_id(self, serialized_matches, action_queue=False):
        """Return the first high-value match to focus when the board opens."""
        if action_queue:
            return action_queue[0]["match_id"]
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
        action_queue = self._operations_build_action_queue(serialized_matches)
        court_summaries = self._operations_build_court_summaries(serialized_matches)
        summary = self._operations_build_summary(serialized_matches)
        summary.update(
            {
                "blocked_court_count": sum(
                    1
                    for court in court_summaries
                    if court["status"]["key"] == "blocked"
                ),
                "delayed_court_count": sum(
                    1
                    for court in court_summaries
                    if court["status"]["key"] == "delayed"
                ),
                "live_court_count": sum(
                    1 for court in court_summaries if court["status"]["key"] == "live"
                ),
                "action_queue_count": len(action_queue),
            }
        )
        generated_at = self._operations_format_datetime_parts(now_dt)
        return {
            "tournament": self._operations_serialize_tournament(),
            "summary": summary,
            "filters": self._operations_build_filter_options(serialized_matches),
            "matches": serialized_matches,
            "action_queue": action_queue,
            "court_summaries": court_summaries,
            "default_match_id": self._operations_get_default_match_id(
                serialized_matches,
                action_queue=action_queue,
            ),
            "generated_at": generated_at["label"],
            "generated_at_value": generated_at["value"],
        }
