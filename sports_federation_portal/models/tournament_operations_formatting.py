from odoo import _, api, fields

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


class TournamentOperationsFormattingMixin:
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
            return {
                "key": "validation",
                "label": _("Needs validation"),
                "tone": "warning",
            }
        if result_state == "corrected":
            return {"key": "resubmit", "label": _("Corrected"), "tone": "warning"}
        return {"key": "draft", "label": _("Not sent"), "tone": "secondary"}

    @api.model
    def _operations_format_duration_label(self, minutes):
        """Return a short operator-facing duration label."""
        abs_minutes = abs(int(minutes or 0))
        hours, remaining_minutes = divmod(abs_minutes, 60)
        if hours and remaining_minutes:
            return _("%(hours)s h %(minutes)s min") % {
                "hours": hours,
                "minutes": remaining_minutes,
            }
        if hours:
            return _("%(hours)s h") % {"hours": hours}
        return _("%(minutes)s min") % {"minutes": remaining_minutes}

    @api.model
    def _operations_get_schedule_status(self, match, scheduled_dt, now_dt):
        """Return live schedule guidance for one match."""
        if not scheduled_dt:
            return {
                "minutes_to_start": False,
                "is_overdue": False,
                "is_due_soon": False,
                "short_label": _("Time not set"),
                "tone": "secondary",
            }

        delta_minutes = int((scheduled_dt - now_dt).total_seconds() // 60)
        if match.state == "in_progress":
            return {
                "minutes_to_start": delta_minutes,
                "is_overdue": False,
                "is_due_soon": False,
                "short_label": _("Live now"),
                "tone": "primary",
            }
        if match.state == "done":
            return {
                "minutes_to_start": delta_minutes,
                "is_overdue": False,
                "is_due_soon": False,
                "short_label": _("Finished"),
                "tone": "success",
            }
        if match.state == "cancelled":
            return {
                "minutes_to_start": delta_minutes,
                "is_overdue": False,
                "is_due_soon": False,
                "short_label": _("Cancelled"),
                "tone": "dark",
            }

        if delta_minutes < 0:
            return {
                "minutes_to_start": delta_minutes,
                "is_overdue": True,
                "is_due_soon": False,
                "short_label": _("Late by %(duration)s")
                % {"duration": self._operations_format_duration_label(delta_minutes)},
                "tone": "danger",
            }
        if delta_minutes == 0:
            return {
                "minutes_to_start": delta_minutes,
                "is_overdue": False,
                "is_due_soon": True,
                "short_label": _("Starting now"),
                "tone": "warning",
            }
        if delta_minutes <= 30:
            return {
                "minutes_to_start": delta_minutes,
                "is_overdue": False,
                "is_due_soon": True,
                "short_label": _("Starts in %(duration)s")
                % {"duration": self._operations_format_duration_label(delta_minutes)},
                "tone": "warning",
            }
        return {
            "minutes_to_start": delta_minutes,
            "is_overdue": False,
            "is_due_soon": False,
            "short_label": _("Starts in %(duration)s")
            % {"duration": self._operations_format_duration_label(delta_minutes)},
            "tone": "info",
        }

    @api.model
    def _operations_get_match_sheet_status(self, match):
        """Return match-sheet readiness when the rosters addon is installed."""
        if "match_sheet_ids" not in match._fields:
            return {
                "key": False,
                "label": False,
                "tone": "secondary",
                "draft_count": 0,
                "submitted_count": 0,
                "ready_count": 0,
                "total_count": 0,
            }

        sheets = match.match_sheet_ids
        total_count = len(sheets)
        if not total_count:
            return {
                "key": "missing",
                "label": _("Match sheets missing"),
                "tone": "warning",
                "draft_count": 0,
                "submitted_count": 0,
                "ready_count": 0,
                "total_count": 0,
            }

        draft_count = len(sheets.filtered(lambda sheet: sheet.state == "draft"))
        submitted_count = len(sheets.filtered(lambda sheet: sheet.state == "submitted"))
        ready_count = len(
            sheets.filtered(lambda sheet: sheet.state in ("approved", "locked"))
        )

        if draft_count:
            label = _("%(count)s team sheet(s) still draft") % {
                "count": draft_count,
            }
            key = "draft"
            tone = "warning"
        elif submitted_count:
            label = _("%(count)s team sheet(s) waiting for approval") % {
                "count": submitted_count,
            }
            key = "submitted"
            tone = "info"
        else:
            label = _("Team sheets ready")
            key = "ready"
            tone = "success"

        return {
            "key": key,
            "label": label,
            "tone": tone,
            "draft_count": draft_count,
            "submitted_count": submitted_count,
            "ready_count": ready_count,
            "total_count": total_count,
        }

    @api.model
    def _operations_get_next_step(
        self, match, actions, schedule_status, match_sheet_status
    ):
        """Return the clearest next operator action for one match."""
        pre_match_urgency = 6 if schedule_status["is_due_soon"] else 18
        pre_match_gate = match.state in ("draft", "scheduled")
        primary_action = actions["primary_action"]
        primary_action_key = primary_action["key"]

        if match.state == "cancelled":
            return {
                "key": "cancelled",
                "label": _("Cancelled"),
                "tone": "dark",
                "owner_label": _("No action"),
                "urgency_weight": 99,
            }

        if pre_match_gate and "venue_id" in match._fields and not match.venue_id:
            return {
                "key": "assign_venue",
                "label": _("Assign venue"),
                "tone": "danger",
                "owner_label": _("Court manager"),
                "urgency_weight": pre_match_urgency,
            }

        if (
            pre_match_gate
            and "playing_area_id" in match._fields
            and not match.playing_area_id
        ):
            return {
                "key": "assign_court",
                "label": _("Assign court"),
                "tone": "danger",
                "owner_label": _("Court manager"),
                "urgency_weight": pre_match_urgency + 1,
            }

        if pre_match_gate and match_sheet_status["key"] == "missing":
            return {
                "key": "collect_team_sheet",
                "label": _("Create team sheets"),
                "tone": "warning",
                "owner_label": _("Match desk"),
                "urgency_weight": pre_match_urgency + 2,
            }

        if pre_match_gate and match_sheet_status["key"] == "draft":
            return {
                "key": "collect_team_sheet",
                "label": _("Collect team sheet"),
                "tone": "warning",
                "owner_label": _("Team manager"),
                "urgency_weight": pre_match_urgency + 2,
            }

        if pre_match_gate and match_sheet_status["key"] == "submitted":
            return {
                "key": "approve_team_sheet",
                "label": _("Approve team sheet"),
                "tone": "info",
                "owner_label": _("Match desk"),
                "urgency_weight": pre_match_urgency + 3,
            }

        if (
            pre_match_gate
            and "missing_referees_count" in match._fields
            and match.missing_referees_count
        ):
            return {
                "key": "fix_officiating",
                "label": _("Find missing official"),
                "tone": "danger",
                "owner_label": _("Referee coordinator"),
                "urgency_weight": pre_match_urgency + 4,
            }

        if (
            pre_match_gate
            and "overdue_referee_confirmation_count" in match._fields
            and match.overdue_referee_confirmation_count
        ):
            return {
                "key": "confirm_officiating",
                "label": _("Confirm referee"),
                "tone": "warning",
                "owner_label": _("Referee coordinator"),
                "urgency_weight": pre_match_urgency + 5,
            }

        if primary_action_key == "start" and schedule_status["is_overdue"]:
            return {
                "key": primary_action_key,
                "label": _("Start or reschedule"),
                "tone": "danger",
                "owner_label": _("Court manager"),
                "urgency_weight": 4,
            }

        if match.state == "done" and match.result_state in ("draft", "corrected"):
            return {
                "key": "submit",
                "label": _("Send result for check"),
                "tone": "warning",
                "owner_label": _("Result table"),
                "urgency_weight": 5,
            }

        if match.result_state == "submitted":
            return {
                "key": "verify",
                "label": _("Check result"),
                "tone": "info",
                "owner_label": _("Result checker"),
                "urgency_weight": 6,
            }

        if match.result_state == "verified":
            return {
                "key": "approve",
                "label": _("Make official"),
                "tone": "success",
                "owner_label": _("Approver"),
                "urgency_weight": 7,
            }

        if match.result_state == "contested":
            return {
                "key": "contest",
                "label": _("Resolve review"),
                "tone": "danger",
                "owner_label": _("Federation admin"),
                "urgency_weight": 8,
            }

        if primary_action_key == "finish":
            return {
                "key": primary_action_key,
                "label": _("Finish the match"),
                "tone": "primary",
                "owner_label": _("Result table"),
                "urgency_weight": 20,
            }

        if primary_action_key == "start":
            return {
                "key": primary_action_key,
                "label": _("Prepare kickoff"),
                "tone": schedule_status["tone"],
                "owner_label": _("Court manager"),
                "urgency_weight": 30 if schedule_status["is_due_soon"] else 45,
            }

        if primary_action_key == "schedule":
            return {
                "key": primary_action_key,
                "label": _("Schedule the match"),
                "tone": "secondary",
                "owner_label": _("Tournament admin"),
                "urgency_weight": 60,
            }

        if match.state == "in_progress":
            return {
                "key": "live_monitor",
                "label": _("Monitor live match"),
                "tone": "primary",
                "owner_label": _("Court team"),
                "urgency_weight": 35,
            }

        return {
            "key": "complete",
            "label": _("No urgent action"),
            "tone": "success" if match.result_state == "approved" else "secondary",
            "owner_label": (
                _("Complete") if match.result_state == "approved" else _("Watchlist")
            ),
            "urgency_weight": 90,
        }
