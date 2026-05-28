from odoo import _, fields, models


class CompetitionWorkspaceVenueExtension(models.AbstractModel):
    _name = "federation.competition.workspace.extension.venues"
    _description = "Competition Workspace Venue Extension"

    def _slot_blackout_windows(self, slot):
        blackout_model = self.env["federation.venue.blackout"]
        if not slot or not slot.venue_id or not slot.start_datetime or not slot.end_datetime:
            return blackout_model
        return blackout_model.search(
            [
                ("active", "=", True),
                ("venue_id", "=", slot.venue_id.id),
                ("date_start", "<", fields.Datetime.to_string(slot.end_datetime)),
                ("date_end", ">", fields.Datetime.to_string(slot.start_datetime)),
                "|",
                ("playing_area_id", "=", False),
                ("playing_area_id", "=", slot.playing_area_id.id),
            ]
        )

    def _capability_gap_issue(self, match, slot):
        required_capabilities = match.tournament_id.required_playing_area_capability_ids
        if not required_capabilities or not slot.playing_area_id:
            return False
        missing_capabilities = required_capabilities - slot.playing_area_id.capability_ids
        if not missing_capabilities:
            return False
        return {
            "code": "venue_capability_mismatch",
            "message": _(
                "%(court)s is missing required capabilities for %(division)s: %(capabilities)s.",
                court=slot.playing_area_id.display_name,
                division=match.tournament_id.display_name,
                capabilities=", ".join(missing_capabilities.mapped("name")),
            ),
            "record_id": match.id,
            "match_id": match.id,
            "slot_id": slot.id,
        }

    def _slot_constraint_issues(self, match, slot):
        blocking = []
        for window in self._slot_blackout_windows(slot):
            blocking.append(
                {
                    "code": (
                        "venue_maintenance"
                        if window.closure_type == "maintenance"
                        else "venue_blackout"
                    ),
                    "message": _(
                        "%(venue)s is unavailable for %(match)s because %(window)s overlaps this slot.",
                        venue=slot.venue_id.display_name,
                        match=match.display_name,
                        window=window.name,
                    ),
                    "record_id": match.id,
                    "match_id": match.id,
                    "slot_id": slot.id,
                }
            )
        capability_issue = self._capability_gap_issue(match, slot)
        if capability_issue:
            blocking.append(capability_issue)
        return blocking

    def _scheduled_matches(self, records):
        return records.filtered(lambda match: match.slot_id)

    def _venue_summary(self, matches):
        matches = self._scheduled_matches(matches)
        summary = {
            "scheduled_match_count": len(matches),
            "clear_match_count": 0,
            "attention_match_count": 0,
            "blackout_match_count": 0,
            "maintenance_match_count": 0,
            "capability_issue_match_count": 0,
        }
        for match in matches:
            issues = self._slot_constraint_issues(match, match.slot_id)
            if not issues:
                summary["clear_match_count"] += 1
                continue
            summary["attention_match_count"] += 1
            codes = {issue["code"] for issue in issues}
            if "venue_blackout" in codes:
                summary["blackout_match_count"] += 1
            if "venue_maintenance" in codes:
                summary["maintenance_match_count"] += 1
            if "venue_capability_mismatch" in codes:
                summary["capability_issue_match_count"] += 1
        return summary

    def extend_match_assignment_validation(
        self,
        workspace_service,
        match,
        slot,
        effective_slots=False,
    ):
        return {"blocking": self._slot_constraint_issues(match, slot), "warnings": []}

    def extend_match_card(self, workspace_service, match, payload=False):
        if not match.slot_id:
            return {}
        issues = self._slot_constraint_issues(match, match.slot_id)
        return {
            "venue_readiness": {
                "ready": not issues,
                "blocking_count": len(issues),
                "issues": issues,
            }
        }

    def extend_gameday_payload(self, workspace_service, gameday, payload=False):
        planner_root = workspace_service._get_planner_root_gameday(gameday)
        matches = planner_root.slot_ids.filtered("match_id").mapped("match_id")
        return {"venue_summary": self._venue_summary(matches)}

    def extend_division_payload(self, workspace_service, division, payload=False):
        return {"venue_summary": self._venue_summary(division.match_ids)}

    def extend_overview_payload(
        self,
        workspace_service,
        competition,
        divisions,
        payload=False,
    ):
        summary = {
            "scheduled_match_count": 0,
            "clear_match_count": 0,
            "attention_match_count": 0,
            "blackout_match_count": 0,
            "maintenance_match_count": 0,
            "capability_issue_match_count": 0,
        }
        for division in divisions:
            division_summary = self._venue_summary(division.match_ids)
            for key, value in division_summary.items():
                summary[key] += value
        return {"venue_summary": summary}