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
        return planner_root.planner_state in (
            "published",
            "locked",
            "in_progress",
            "completed",
        )

    @staticmethod
    def _windows_overlap(start_a, end_a, start_b, end_b):
        return bool(start_a and start_b and not (end_a <= start_b or end_b <= start_a))

    @staticmethod
    def _match_club_ids(match):
        return set((match.home_team_id.club_id | match.away_team_id.club_id).ids)

    def _club_duty_conflicts(
        self,
        workspace_service,
        match,
        slot,
        effective_slots=False,
    ):
        """Detect a club playing while supplying an overlapping official duty."""
        if "club_referee_duty_ids" not in match._fields:
            return []
        target_start, target_end = self._match_window(
            match, slot=slot, effective_slots=effective_slots
        )
        if not target_start:
            return []

        planner_root = workspace_service._get_planner_root_gameday(slot.round_id)
        planner_matches = (
            planner_root.slot_ids.filtered("match_id").mapped("match_id") | match
        )
        target_playing_clubs = self._match_club_ids(match)
        conflicts = []
        seen = set()

        for other in planner_matches:
            if other == match:
                continue
            other_slot = (effective_slots or {}).get(other.id) or other.slot_id
            other_start, other_end = self._match_window(
                other, slot=other_slot, effective_slots=effective_slots
            )
            if not self._windows_overlap(
                target_start, target_end, other_start, other_end
            ):
                continue

            for duty in other.club_referee_duty_ids.filtered(
                lambda item: item.state != "draft"
                and item.club_id.id in target_playing_clubs
            ):
                key = (duty.id, match.id, other.id)
                if key in seen:
                    continue
                seen.add(key)
                conflicts.append(
                    self._club_duty_overlap_issue(
                        duty=duty,
                        playing_match=match,
                        duty_match=other,
                        slot=slot,
                    )
                )

            other_playing_clubs = self._match_club_ids(other)
            for duty in match.club_referee_duty_ids.filtered(
                lambda item: item.state != "draft"
                and item.club_id.id in other_playing_clubs
            ):
                key = (duty.id, other.id, match.id)
                if key in seen:
                    continue
                seen.add(key)
                conflicts.append(
                    self._club_duty_overlap_issue(
                        duty=duty,
                        playing_match=other,
                        duty_match=match,
                        slot=slot,
                    )
                )
        return conflicts

    @staticmethod
    def _club_duty_overlap_issue(duty, playing_match, duty_match, slot):
        role_label = dict(duty._fields["role"].selection).get(duty.role, duty.role)
        return {
            "code": "club_duty_play_overlap",
            "message": _(
                "%(club)s cannot play %(playing_match)s while supplying %(role)s "
                "for %(duty_match)s in the same timeslot.",
                club=duty.club_id.display_name,
                playing_match=playing_match.display_name,
                role=role_label,
                duty_match=duty_match.display_name,
            ),
            "record_id": playing_match.id,
            "match_id": playing_match.id,
            "slot_id": slot.id,
            "duty_id": duty.id,
            "club_id": duty.club_id.id,
        }

    def extend_match_assignment_validation(
        self,
        workspace_service,
        match,
        slot,
        effective_slots=False,
    ):
        if "referee_assignment_ids" not in match._fields:
            return {}
        duty_conflicts = self._club_duty_conflicts(
            workspace_service,
            match,
            slot,
            effective_slots=effective_slots,
        )
        if not self._officiating_checks_active_for_planner(
            workspace_service, slot.round_id
        ):
            return {"blocking": duty_conflicts, "warnings": []}
        target_start, target_end = self._match_window(
            match,
            slot=slot,
            effective_slots=effective_slots,
        )
        if not target_start:
            return {}

        blocking = list(duty_conflicts)
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
        if (
            "referee_assignment_ids"
            not in workspace_service.env["federation.match"]._fields
        ):
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
                            issues=(match.official_readiness_issues or "").replace(
                                "\n", "; "
                            ),
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
        active_duties = (
            match.club_referee_duty_ids.filtered(lambda duty: duty.state != "draft")
            if "club_referee_duty_ids" in match._fields
            else self.env["federation.match.club.referee.duty"]
        )
        return {
            "officiating": {
                "required_count": match.required_referee_count,
                "confirmed_count": match.confirmed_referee_count,
                "ready": match.is_officially_ready,
                "issues": match.official_readiness_issues or False,
                "warning_count": len(officiating_warnings),
                "warnings": officiating_warnings,
                "club_duty_count": len(active_duties),
                "club_duties": [
                    {
                        "id": duty.id,
                        "club_id": duty.club_id.id,
                        "club_name": duty.club_id.display_name,
                        "role": duty.role,
                        "role_label": dict(duty._fields["role"].selection).get(
                            duty.role, duty.role
                        ),
                        "state": duty.state,
                        "state_label": dict(duty._fields["state"].selection).get(
                            duty.state, duty.state
                        ),
                    }
                    for duty in active_duties
                ],
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
            division_summary = self._officiating_summary(
                division.match_ids.filtered("slot_id")
            )
            for key, value in division_summary.items():
                summary[key] += value
        return {"officiating_summary": summary}
