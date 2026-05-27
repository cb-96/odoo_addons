from odoo import _, api, fields, models


class CompetitionWorkspaceValidationService(models.AbstractModel):
    _name = "federation.competition.workspace.validation.service"
    _description = "Competition Workspace Validation Service"

    def _build_validation_result(self):
        return {
            "valid": True,
            "blocking": [],
            "warnings": [],
            "blocking_groups": [],
            "warning_groups": [],
            "unscheduled_matches": [],
            "empty_slots": [],
        }

    def _issue_defaults(self):
        return {
            "approved_result_locked": {
                "group_key": "match_state",
                "group_label": _("Match state locks"),
                "hint": _(
                    "Move the match only after a federation manager has reviewed the approved result."
                ),
                "focus_target": "match",
            },
            "back_to_back": {
                "group_key": "team_conflicts",
                "group_label": _("Team availability"),
                "hint": _(
                    "Move one of the matches so the shared team gets a recovery window."
                ),
                "focus_target": "team",
            },
            "team_consecutive_limit": {
                "group_key": "team_conflicts",
                "group_label": _("Team availability"),
                "hint": _(
                    "Adjust slots or raise the division consecutive-match limit before retrying."
                ),
                "focus_target": "team",
            },
            "bulk_assign_requires_unscheduled": {
                "group_key": "selection",
                "group_label": _("Selection issues"),
                "hint": _(
                    "Clear already assigned matches from the bulk selection before retrying."
                ),
                "focus_target": "match",
            },
            "bulk_unassign_requires_assigned": {
                "group_key": "selection",
                "group_label": _("Selection issues"),
                "hint": _(
                    "Only matches that are currently on the planner can be bulk-unassigned."
                ),
                "focus_target": "match",
            },
            "cross_division_slot": {
                "group_key": "slot_conflicts",
                "group_label": _("Slot conflicts"),
                "hint": _(
                    "Pick a slot from the same shared gameday group as the match division."
                ),
                "focus_target": "slot",
            },
            "cross_gameday_selection": {
                "group_key": "selection",
                "group_label": _("Selection issues"),
                "hint": _(
                    "Keep bulk edits scoped to the matches already assigned on the active gameday."
                ),
                "focus_target": "match",
            },
            "insufficient_open_slots": {
                "group_key": "slot_conflicts",
                "group_label": _("Slot conflicts"),
                "hint": _(
                    "Generate more slots or reduce the selected match set before retrying."
                ),
                "focus_target": "slot",
            },
            "match_locked": {
                "group_key": "match_state",
                "group_label": _("Match state locks"),
                "hint": _(
                    "Live, completed, or cancelled matches must stay on their current schedule."
                ),
                "focus_target": "match",
            },
            "missing_referee": {
                "group_key": "readiness",
                "group_label": _("Readiness checks"),
                "hint": _(
                    "Add a referee assignment before final publication if officiating is required."
                ),
                "focus_target": "match",
            },
            "officiating_not_ready": {
                "group_key": "readiness",
                "group_label": _("Readiness checks"),
                "hint": _(
                    "Resolve officiating readiness before publishing the schedule."
                ),
                "focus_target": "match",
            },
            "no_redo_available": {
                "group_key": "history",
                "group_label": _("History"),
                "hint": _("No newer undone planner action is available to replay."),
                "focus_target": "history",
            },
            "no_selected_matches": {
                "group_key": "selection",
                "group_label": _("Selection issues"),
                "hint": _(
                    "Select at least one planner card before running the bulk action."
                ),
                "focus_target": "selection",
            },
            "no_undo_available": {
                "group_key": "history",
                "group_label": _("History"),
                "hint": _("There is no earlier planner action left to undo."),
                "focus_target": "history",
            },
            "override_reason_required": {
                "group_key": "manager_override",
                "group_label": _("Manager override"),
                "hint": _(
                    "Enter a short manager reason so the override can be audited later."
                ),
                "focus_target": "publish",
            },
            "published_match_locked": {
                "group_key": "match_state",
                "group_label": _("Match state locks"),
                "hint": _(
                    "Use a federation manager account before changing published or locked matches."
                ),
                "focus_target": "match",
            },
            "referee_double_booked": {
                "group_key": "readiness",
                "group_label": _("Readiness checks"),
                "hint": _(
                    "Reassign the official or move one of the overlapping matches."
                ),
                "focus_target": "match",
            },
            "referee_unavailable": {
                "group_key": "readiness",
                "group_label": _("Readiness checks"),
                "hint": _(
                    "Record a covering availability window or choose another official before publication."
                ),
                "focus_target": "match",
            },
            "short_rest": {
                "group_key": "team_conflicts",
                "group_label": _("Team availability"),
                "hint": _(
                    "Choose a later slot or another court so the team meets the rest policy."
                ),
                "focus_target": "team",
            },
            "slot_occupied": {
                "group_key": "slot_conflicts",
                "group_label": _("Slot conflicts"),
                "hint": _(
                    "Unassign or move the conflicting match before reusing this slot."
                ),
                "focus_target": "slot",
            },
            "slot_unavailable": {
                "group_key": "slot_conflicts",
                "group_label": _("Slot conflicts"),
                "hint": _(
                    "Choose a playable slot instead of a break, locked, or unavailable window."
                ),
                "focus_target": "slot",
            },
            "venue_blackout": {
                "group_key": "venue_constraints",
                "group_label": _("Venue constraints"),
                "hint": _(
                    "Move the match outside the blackout window or choose another court or day."
                ),
                "focus_target": "slot",
            },
            "venue_capability_mismatch": {
                "group_key": "venue_constraints",
                "group_label": _("Venue constraints"),
                "hint": _(
                    "Choose a court with the required capability tags or update the division venue requirements."
                ),
                "focus_target": "slot",
            },
            "venue_maintenance": {
                "group_key": "venue_constraints",
                "group_label": _("Venue constraints"),
                "hint": _(
                    "Reschedule the match away from the maintenance closure."
                ),
                "focus_target": "slot",
            },
            "team_overlap": {
                "group_key": "team_conflicts",
                "group_label": _("Team availability"),
                "hint": _(
                    "Keep the shared team out of overlapping timeslots on the same gameday."
                ),
                "focus_target": "team",
            },
        }

    def _decorate_issue(self, issue, severity):
        issue = dict(issue)
        defaults = self._issue_defaults().get(issue.get("code"), {})
        issue.setdefault("severity", severity)
        issue.setdefault("group_key", defaults.get("group_key", "other"))
        issue.setdefault("group_label", defaults.get("group_label", _("Other issues")))
        issue.setdefault(
            "hint",
            defaults.get(
                "hint",
                _("Review this issue in the planner before continuing."),
            ),
        )
        issue.setdefault("focus_target", defaults.get("focus_target", "issue"))
        issue.setdefault(
            "focus_record_id",
            issue.get("slot_id") or issue.get("match_id") or issue.get("record_id") or False,
        )
        return issue

    def _group_issues(self, issues):
        grouped = {}
        for issue in issues:
            key = issue.get("group_key") or "other"
            if key not in grouped:
                grouped[key] = {
                    "key": key,
                    "label": issue.get("group_label") or _("Other issues"),
                    "severity": issue.get("severity") or "warning",
                    "count": 0,
                    "issues": [],
                }
            grouped[key]["count"] += 1
            grouped[key]["issues"].append(issue)
        return [
            grouped[key]
            for key in sorted(
                grouped,
                key=lambda item: (grouped[item]["severity"], grouped[item]["label"], item),
            )
        ]

    @api.model
    def finalize_validation_result(self, result):
        blocking = [
            self._decorate_issue(issue, "blocking")
            for issue in (result.get("blocking") or [])
        ]
        warnings = [
            self._decorate_issue(issue, "warning")
            for issue in (result.get("warnings") or [])
        ]
        result["blocking"] = blocking
        result["warnings"] = warnings
        result["blocking_groups"] = self._group_issues(blocking)
        result["warning_groups"] = self._group_issues(warnings)
        return result

    def _append_issue(self, issues, issue, dedupe):
        signature = (issue.get("code"), issue.get("record_id"), issue.get("message"))
        if signature in dedupe:
            return
        dedupe.add(signature)
        issues.append(issue)

    def _get_gameday_validation_slots(self, workspace_service, gameday):
        planner_root = workspace_service._get_planner_root_gameday(gameday)
        return planner_root.slot_ids.sorted(
            lambda record: (record.start_datetime, record.playing_area_id.id, record.id)
        )

    def match_move_blocking_issue(self, workspace_service, match, capabilities):
        if match.state in ("in_progress", "done", "cancelled"):
            return {
                "code": "match_locked",
                "message": _(
                    "This match is already live, completed, or cancelled and cannot be moved."
                ),
                "record_id": match.id,
                "match_id": match.id,
            }
        if match.slot_id and match.slot_id.round_id.planner_state in (
            "published",
            "locked",
            "in_progress",
            "completed",
        ) and not capabilities["is_manager"]:
            return {
                "code": "published_match_locked",
                "message": _(
                    "Published or locked matches can only be moved by a federation manager."
                ),
                "record_id": match.id,
                "match_id": match.id,
            }
        if (
            "result_state" in match._fields
            and match.result_state == "approved"
            and not capabilities["is_manager"]
        ):
            return {
                "code": "approved_result_locked",
                "message": _(
                    "Matches with approved results can only be rescheduled by a federation manager."
                ),
                "record_id": match.id,
                "match_id": match.id,
            }
        return False

    def _compute_rest_gap_minutes(self, slot, other_slot):
        if other_slot.end_datetime <= slot.start_datetime:
            return int((slot.start_datetime - other_slot.end_datetime).total_seconds() / 60)
        if slot.end_datetime <= other_slot.start_datetime:
            return int((other_slot.start_datetime - slot.end_datetime).total_seconds() / 60)
        return None

    def _effective_slot_for_match(self, match, simulated_slots=None):
        if simulated_slots and match.id in simulated_slots:
            return simulated_slots[match.id]
        return match.slot_id

    def _rest_gap_is_consecutive(self, rest_gap, minimum_rest_minutes):
        if rest_gap is None or rest_gap < 0:
            return False
        threshold = minimum_rest_minutes if minimum_rest_minutes > 0 else 1
        return rest_gap < threshold

    def _effective_slot_match(self, slot, simulated_slots=None, match_id=False):
        for simulated_match_id, simulated_slot in (simulated_slots or {}).items():
            if simulated_slot and simulated_slot == slot and simulated_match_id != match_id:
                return self.env["federation.match"].browse(simulated_match_id).exists()
        current_match = slot.match_id.exists()
        if current_match and current_match.id != match_id and (
            not simulated_slots or current_match.id not in simulated_slots
        ):
            return current_match
        return False

    def _planner_root_effective_assignments(
        self,
        workspace_service,
        planner_root,
        simulated_slots=None,
    ):
        assignments = {}
        normalized_slots = simulated_slots or {}
        for slot in planner_root.slot_ids.filtered("match_id"):
            match = slot.match_id.exists()
            if not match:
                continue
            effective_slot = normalized_slots.get(match.id, slot)
            if effective_slot:
                assignments[match.id] = (match, effective_slot)
            elif match.id in assignments:
                assignments.pop(match.id, None)
        for match_id, effective_slot in normalized_slots.items():
            if not effective_slot or match_id in assignments:
                continue
            match = self.env["federation.match"].browse(match_id).exists()
            if match:
                assignments[match.id] = (match, effective_slot)
        return list(assignments.values())

    def _team_schedule_warnings(self, match, slot, simulated_slots=None):
        warnings = []
        min_rest_minutes = max(match.tournament_id.minimum_rest_minutes or 0, 0)
        max_consecutive_matches = max(
            match.tournament_id.max_consecutive_matches_per_team or 1,
            1,
        )
        team_ids = [match.home_team_id.id, match.away_team_id.id]
        warning_domain = [
            ("id", "!=", match.id),
            ("tournament_id", "=", match.tournament_id.id),
        ]
        if simulated_slots:
            warning_domain.extend(
                ["|", ("slot_id", "!=", False), ("id", "in", list(simulated_slots))]
            )
        else:
            warning_domain.append(("slot_id", "!=", False))
        other_matches = self.env["federation.match"].search(
            warning_domain
        )
        team_windows = {
            team_id: [
                {
                    "match_id": match.id,
                    "slot_id": slot.id,
                    "start": slot.start_datetime,
                    "end": slot.end_datetime,
                }
            ]
            for team_id in team_ids
            if team_id
        }
        for other_match in other_matches:
            other_slot = self._effective_slot_for_match(other_match, simulated_slots)
            if not other_slot:
                continue
            if other_slot.start_datetime.date() != slot.start_datetime.date():
                continue
            shared_team_ids = set(team_ids) & {
                other_match.home_team_id.id,
                other_match.away_team_id.id,
            }
            if not shared_team_ids:
                continue
            for team_id in shared_team_ids:
                team_windows.setdefault(team_id, []).append(
                    {
                        "match_id": other_match.id,
                        "slot_id": other_slot.id,
                        "start": other_slot.start_datetime,
                        "end": other_slot.end_datetime,
                    }
                )
            rest_gap = self._compute_rest_gap_minutes(slot, other_slot)
            if rest_gap is None:
                continue
            if rest_gap == 0 and max_consecutive_matches <= 1:
                warnings.append(
                    {
                        "code": "back_to_back",
                        "message": _(
                            "A team would play back-to-back matches with no rest window."
                        ),
                        "record_id": other_match.id,
                        "match_id": other_match.id,
                        "slot_id": other_slot.id,
                        "team_ids": list(shared_team_ids),
                    }
                )
            elif min_rest_minutes and rest_gap < min_rest_minutes:
                warnings.append(
                    {
                        "code": "short_rest",
                        "message": _(
                            "Rest time is shorter than the configured minimum of %(minutes)s minutes.",
                            minutes=min_rest_minutes,
                        ),
                        "record_id": other_match.id,
                        "match_id": other_match.id,
                        "slot_id": other_slot.id,
                        "team_ids": list(shared_team_ids),
                    }
                )
        for team_id, windows in team_windows.items():
            if len(windows) <= 1:
                continue
            ordered_windows = sorted(
                windows,
                key=lambda item: (item["start"], item["end"], item["match_id"]),
            )
            consecutive_run = 1
            for current_index in range(1, len(ordered_windows)):
                previous_window = ordered_windows[current_index - 1]
                current_window = ordered_windows[current_index]
                rest_gap = int(
                    (
                        current_window["start"] - previous_window["end"]
                    ).total_seconds()
                    / 60
                )
                if self._rest_gap_is_consecutive(rest_gap, min_rest_minutes):
                    consecutive_run += 1
                else:
                    consecutive_run = 1
                if consecutive_run > max_consecutive_matches:
                    team = self.env["federation.team"].browse(team_id)
                    warnings.append(
                        {
                            "code": "team_consecutive_limit",
                            "message": _(
                                "%(team)s would play %(count)s consecutive matches with short rest (limit: %(limit)s).",
                                team=team.display_name,
                                count=consecutive_run,
                                limit=max_consecutive_matches,
                            ),
                            "record_id": current_window["match_id"],
                            "match_id": current_window["match_id"],
                            "slot_id": current_window["slot_id"],
                            "team_ids": [team_id],
                        }
                    )
                    break
        return warnings

    @api.model
    def validate_match_assignment(
        self,
        workspace_service,
        match_id,
        slot_id,
        simulated_slots=None,
    ):
        capabilities = workspace_service._check_access()
        match = workspace_service._resolve_match(match_id)
        slot = workspace_service._resolve_slot(slot_id)
        slot_root = workspace_service._get_planner_root_gameday(slot.round_id)
        result = self._build_validation_result()
        blocking_seen = set()
        warning_seen = set()
        effective_slots = simulated_slots or {}

        target_round = workspace_service._get_match_planner_round(slot_root, match)
        if not target_round:
            self._append_issue(
                result["blocking"],
                {
                    "code": "cross_division_slot",
                    "message": _(
                        "Matches can only be assigned to slots from divisions linked to this shared gameday."
                    ),
                    "record_id": slot.id,
                    "match_id": match.id,
                    "slot_id": slot.id,
                },
                blocking_seen,
            )

        blocking_issue = self.match_move_blocking_issue(
            workspace_service, match, capabilities
        )
        if blocking_issue:
            self._append_issue(result["blocking"], blocking_issue, blocking_seen)

        if slot.state not in ("available", "reserved", "assigned"):
            self._append_issue(
                result["blocking"],
                {
                    "code": "slot_unavailable",
                    "message": _("The target slot is not available for assignment."),
                    "record_id": slot.id,
                    "match_id": match.id,
                    "slot_id": slot.id,
                },
                blocking_seen,
            )

        occupying_match = self._effective_slot_match(
            slot,
            effective_slots,
            match_id=match.id,
        )
        if occupying_match and occupying_match != match:
            self._append_issue(
                result["blocking"],
                {
                    "code": "slot_occupied",
                    "message": _(
                        "The target slot is already occupied by another match."
                    ),
                    "record_id": occupying_match.id,
                    "match_id": occupying_match.id,
                    "slot_id": slot.id,
                },
                blocking_seen,
            )

        target_team_ids = {match.home_team_id.id, match.away_team_id.id}
        for other_match, other_slot in self._planner_root_effective_assignments(
            workspace_service,
            slot_root,
            effective_slots,
        ):
            if other_match == match or other_slot == slot:
                continue
            if (
                other_slot.start_datetime >= slot.end_datetime
                or other_slot.end_datetime <= slot.start_datetime
            ):
                continue
            if target_team_ids & {
                other_match.home_team_id.id,
                other_match.away_team_id.id,
            }:
                self._append_issue(
                    result["blocking"],
                    {
                        "code": "team_overlap",
                        "message": _("Team already plays in this timeslot."),
                        "record_id": other_match.id,
                        "match_id": other_match.id,
                        "slot_id": other_slot.id,
                        "team_ids": list(
                            target_team_ids
                            & {
                                other_match.home_team_id.id,
                                other_match.away_team_id.id,
                            }
                        ),
                    },
                    blocking_seen,
                )

        for warning in self._team_schedule_warnings(
            match,
            slot,
            simulated_slots=effective_slots,
        ):
            self._append_issue(result["warnings"], warning, warning_seen)

        extension_issues = workspace_service._workspace_extension_issues(
            "extend_match_assignment_validation",
            match,
            slot,
            effective_slots=effective_slots,
        )
        for issue in extension_issues["blocking"]:
            self._append_issue(result["blocking"], issue, blocking_seen)
        for issue in extension_issues["warnings"]:
            self._append_issue(result["warnings"], issue, warning_seen)

        result["valid"] = not result["blocking"]
        return self.finalize_validation_result(result)

    def _validate_division_schedule(self, workspace_service, division):
        result = self._build_validation_result()
        blocking_seen = set()
        warning_seen = set()
        for gameday in workspace_service._get_division_gamedays(division):
            day_result = self.validate_gameday(workspace_service, gameday.id)
            for issue in day_result["blocking"]:
                self._append_issue(result["blocking"], issue, blocking_seen)
            for issue in day_result["warnings"]:
                self._append_issue(result["warnings"], issue, warning_seen)
            result["empty_slots"].extend(day_result["empty_slots"])
        for match in workspace_service._get_unscheduled_matches(division):
            result["unscheduled_matches"].append(
                {
                    "match_id": match.id,
                    "message": _(
                        "%(match)s is still unscheduled.", match=match.display_name
                    ),
                }
            )
        result["valid"] = not result["blocking"] and not result["unscheduled_matches"]
        return self.finalize_validation_result(result)

    @api.model
    def validate_gameday(self, workspace_service, gameday_id):
        workspace_service._check_access()
        gameday = workspace_service._resolve_gameday(gameday_id)
        result = self._build_validation_result()
        blocking_seen = set()
        warning_seen = set()
        for slot in self._get_gameday_validation_slots(workspace_service, gameday):
            if not slot.match_id:
                result["empty_slots"].append(
                    {
                        "slot_id": slot.id,
                        "message": _("%(slot)s is empty.", slot=slot.display_name),
                    }
                )
                continue
            slot_validation = self.validate_match_assignment(
                workspace_service, slot.match_id.id, slot.id
            )
            for issue in slot_validation["blocking"]:
                self._append_issue(result["blocking"], issue, blocking_seen)
            for issue in slot_validation["warnings"]:
                self._append_issue(result["warnings"], issue, warning_seen)
        extension_issues = workspace_service._workspace_extension_issues(
            "extend_gameday_validation",
            gameday,
        )
        for issue in extension_issues["blocking"]:
            self._append_issue(result["blocking"], issue, blocking_seen)
        for issue in extension_issues["warnings"]:
            self._append_issue(result["warnings"], issue, warning_seen)
        result["valid"] = not result["blocking"]
        return self.finalize_validation_result(result)

    @api.model
    def validate_competition_schedule(
        self, workspace_service, competition_id=False, division_id=False
    ):
        workspace_service._check_access()
        if division_id:
            return self._validate_division_schedule(
                workspace_service, workspace_service._resolve_division(division_id)
            )
        competition = workspace_service._resolve_competition(competition_id)
        result = self._build_validation_result()
        blocking_seen = set()
        warning_seen = set()
        empty_slot_seen = set()
        for division in competition.tournament_ids.sorted(
            lambda record: (record.date_start or fields.Date.today(), record.name or "", record.id)
        ):
            division_result = self._validate_division_schedule(workspace_service, division)
            for issue in division_result["blocking"]:
                self._append_issue(result["blocking"], issue, blocking_seen)
            for issue in division_result["warnings"]:
                self._append_issue(result["warnings"], issue, warning_seen)
            result["unscheduled_matches"].extend(division_result["unscheduled_matches"])
            for empty_slot in division_result["empty_slots"]:
                signature = (empty_slot.get("slot_id"), empty_slot.get("message"))
                if signature in empty_slot_seen:
                    continue
                empty_slot_seen.add(signature)
                result["empty_slots"].append(empty_slot)
        result["valid"] = not result["blocking"] and not result["unscheduled_matches"]
        return self.finalize_validation_result(result)