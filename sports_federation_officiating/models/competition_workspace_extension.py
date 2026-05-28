from datetime import timedelta

from odoo import _, fields, models


class CompetitionWorkspaceOfficiatingExtension(models.AbstractModel):
    _name = "federation.competition.workspace.extension.officiating"
    _description = "Competition Workspace Officiating Extension"

    def _match_window(self, match, slot=False, effective_slots=False):
        slot = slot or (effective_slots or {}).get(match.id)
        if slot and slot.start_datetime:
            start_value = slot.start_datetime
            end_value = slot.end_datetime or slot.start_datetime
            return (
                fields.Datetime.to_datetime(start_value),
                fields.Datetime.to_datetime(end_value),
            )

        slot = match.slot_id if "slot_id" in match._fields else False
        if slot and slot.start_datetime:
            start_value = slot.start_datetime
            end_value = slot.end_datetime or slot.start_datetime
            return (
                fields.Datetime.to_datetime(start_value),
                fields.Datetime.to_datetime(end_value),
            )

        if match.date_scheduled:
            scheduled_at = fields.Datetime.to_datetime(match.date_scheduled)
            return scheduled_at, scheduled_at + timedelta(minutes=1)
        return False, False

    def _active_referee_assignments(self, match):
        if "referee_assignment_ids" not in match._fields:
            return match.env["federation.match.referee"]
        return match.referee_assignment_ids.filtered(
            lambda assignment: assignment.state != "cancelled"
        )

    def _officiating_checks_active_for_planner(self, workspace_service, gameday):
        planner_root = workspace_service._get_planner_root_gameday(gameday)
        return planner_root.planner_state in ("published", "locked", "in_progress", "completed")

    def extend_match_assignment_validation(
        self,
        workspace_service,
        match,
        slot,
        effective_slots=False,
    ):
        if "referee_assignment_ids" not in match._fields:
            return {}
        if not self._officiating_checks_active_for_planner(workspace_service, slot.round_id):
            return {}

        target_start, target_end = self._match_window(
            match,
            slot=slot,
            effective_slots=effective_slots,
        )
        if not target_start:
            return {}

        blocking = []
        warnings = []
        for assignment in self._active_referee_assignments(match):
            overlaps = assignment._get_overlapping_assignments(
                start_dt=target_start,
                end_dt=target_end,
            )
            if overlaps:
                conflicting_assignment = overlaps.sorted(
                    lambda record: (
                        record.match_id.date_scheduled or False,
                        record.match_id.id,
                        record.id,
                    )
                )[:1]
                blocking.append(
                    {
                        "code": "referee_double_booked",
                        "message": _(
                            "%(referee)s is already assigned to %(match)s in an overlapping slot.",
                            referee=assignment.referee_id.display_name,
                            match=conflicting_assignment.match_id.display_name,
                        ),
                        "record_id": match.id,
                        "match_id": match.id,
                        "slot_id": slot.id,
                        "referee_id": assignment.referee_id.id,
                    }
                )
            for warning_message in assignment._get_assignment_warnings(
                start_dt=target_start,
                end_dt=target_end,
            ):
                warnings.append(
                    {
                        "code": "referee_unavailable",
                        "message": _(
                            "%(referee)s availability warning: %(warning)s",
                            referee=assignment.referee_id.display_name,
                            warning=warning_message,
                        ),
                        "record_id": match.id,
                        "match_id": match.id,
                        "slot_id": slot.id,
                        "referee_id": assignment.referee_id.id,
                    }
                )
        return {"blocking": blocking, "warnings": warnings}

    def extend_gameday_validation(self, workspace_service, gameday):
        if "referee_assignment_ids" not in workspace_service.env["federation.match"]._fields:
            return {}
        if not self._officiating_checks_active_for_planner(workspace_service, gameday):
            return {}

        planner_root = workspace_service._get_planner_root_gameday(gameday)
        warnings = []
        for slot in planner_root.slot_ids.filtered("match_id"):
            match = slot.match_id
            if not match.is_officially_ready:
                warnings.append(
                    {
                        "code": "officiating_not_ready",
                        "message": _(
                            "Officiating is not ready for %(match)s: %(issues)s",
                            match=match.display_name,
                            issues=(match.official_readiness_issues or "").replace("\n", "; "),
                        ),
                        "record_id": match.id,
                        "match_id": match.id,
                        "slot_id": slot.id,
                    }
                )
        return {"blocking": [], "warnings": warnings}

    def _officiating_summary(self, matches):
        if not matches or "referee_assignment_ids" not in matches._fields:
            return {}
        warning_count = 0
        blocked_count = 0
        for match in matches:
            if not match.is_officially_ready:
                blocked_count += 1
            if match._get_officiating_warnings():
                warning_count += 1
        return {
            "scheduled_match_count": len(matches),
            "ready_match_count": len(matches.filtered("is_officially_ready")),
            "attention_match_count": blocked_count + warning_count,
            "blocking_match_count": blocked_count,
            "warning_match_count": warning_count,
        }

    def extend_match_card(self, workspace_service, match, payload=False):
        if "referee_assignment_ids" not in match._fields:
            return {}
        officiating_warnings = match._get_officiating_warnings()
        return {
            "officiating": {
                "required_count": match.required_referee_count,
                "confirmed_count": match.confirmed_referee_count,
                "ready": match.is_officially_ready,
                "issues": match.official_readiness_issues or False,
                "warning_count": len(officiating_warnings),
                "warnings": officiating_warnings,
            }
        }

    def extend_gameday_payload(self, workspace_service, gameday, payload=False):
        planner_root = workspace_service._get_planner_root_gameday(gameday)
        matches = planner_root.slot_ids.filtered("match_id").mapped("match_id")
        return {"officiating_summary": self._officiating_summary(matches)}

    def extend_division_payload(self, workspace_service, division, payload=False):
        matches = division.match_ids.filtered("slot_id")
        return {"officiating_summary": self._officiating_summary(matches)}

    def extend_overview_payload(
        self,
        workspace_service,
        competition,
        divisions,
        payload=False,
    ):
        if not divisions:
            return {}
        summary = {
            "scheduled_match_count": 0,
            "ready_match_count": 0,
            "attention_match_count": 0,
            "blocking_match_count": 0,
            "warning_match_count": 0,
        }
        for division in divisions:
            division_summary = self._officiating_summary(division.match_ids.filtered("slot_id"))
            for key, value in division_summary.items():
                summary[key] += value
        return {"officiating_summary": summary}