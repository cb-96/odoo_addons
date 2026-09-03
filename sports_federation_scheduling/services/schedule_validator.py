from odoo import api, models


class FederationScheduleValidator(models.AbstractModel):
    _name = "federation.schedule.validator"
    _description = "Pure Schedule Validator"

    @api.model
    def validate_map(self, schedule, assignment_map):
        errors, warnings = [], []
        fixture_by_id = {
            fixture.id: fixture
            for fixture in schedule.matchday_id.allocation_ids.mapped("fixture_ids")
            if not fixture.bye_team_id
        }
        slot_by_id = {slot.id: slot for slot in schedule.matchday_id.slot_ids}
        used_slots, team_windows = set(), {}
        blackouts = schedule.matchday_id.venue_id.blackout_window_ids.filtered("active")
        for fixture_id, slot_id in assignment_map.items():
            fixture, slot = fixture_by_id.get(fixture_id), slot_by_id.get(slot_id)
            if not fixture or not slot:
                errors.append(
                    {
                        "code": "scope",
                        "message": "Fixture or slot is outside this schedule.",
                    }
                )
                continue
            if fixture.state not in ("ready", "completed"):
                errors.append(
                    {
                        "code": "fixture_not_ready",
                        "message": "Only ready fixtures can be scheduled.",
                        "fixture_id": fixture.id,
                    }
                )
            if not fixture.home_team_id or not fixture.away_team_id:
                errors.append(
                    {
                        "code": "participants_unresolved",
                        "message": "Resolve both fixture participants before scheduling.",
                        "fixture_id": fixture.id,
                    }
                )
            if (
                slot.matchday_id != schedule.matchday_id
                or slot.court_id.venue_id != schedule.matchday_id.venue_id
            ):
                errors.append(
                    {
                        "code": "court_scope",
                        "message": "The selected court does not belong to the match-day venue.",
                        "slot_id": slot.id,
                    }
                )
            if slot_id in used_slots:
                errors.append(
                    {
                        "code": "slot_occupied",
                        "message": "A slot contains more than one fixture.",
                        "slot_id": slot_id,
                    }
                )
            used_slots.add(slot_id)
            if slot.state != "available":
                errors.append(
                    {
                        "code": "slot_unavailable",
                        "message": "The selected slot is not playable.",
                        "slot_id": slot_id,
                    }
                )
            if slot.end_datetime <= slot.start_datetime:
                errors.append(
                    {
                        "code": "invalid_window",
                        "message": "A schedule slot must end after it starts.",
                        "slot_id": slot.id,
                    }
                )
            for blackout in blackouts:
                same_area = (
                    not blackout.playing_area_id
                    or blackout.playing_area_id == slot.court_id
                )
                overlap = (
                    slot.start_datetime < blackout.date_end
                    and blackout.date_start < slot.end_datetime
                )
                if same_area and overlap:
                    errors.append(
                        {
                            "code": "venue_blackout",
                            "message": "The slot overlaps a venue blackout or maintenance window.",
                            "slot_id": slot.id,
                        }
                    )
            for team in (fixture.home_team_id, fixture.away_team_id):
                if not team:
                    continue
                for other_fixture, other_slot in team_windows.get(team.id, []):
                    if (
                        slot.start_datetime < other_slot.end_datetime
                        and other_slot.start_datetime < slot.end_datetime
                    ):
                        errors.append(
                            {
                                "code": "team_overlap",
                                "message": f"{team.display_name} has overlapping fixtures.",
                                "fixture_id": fixture.id,
                                "related_fixture_id": other_fixture.id,
                            }
                        )
                    gap = (
                        min(
                            abs(
                                (
                                    slot.start_datetime - other_slot.end_datetime
                                ).total_seconds()
                            ),
                            abs(
                                (
                                    other_slot.start_datetime - slot.end_datetime
                                ).total_seconds()
                            ),
                        )
                        / 60
                    )
                    if (
                        not (
                            slot.start_datetime < other_slot.end_datetime
                            and other_slot.start_datetime < slot.end_datetime
                        )
                        and gap < schedule.preferred_rest_minutes
                    ):
                        warnings.append(
                            {
                                "code": "rest_shortfall",
                                "message": f"{team.display_name} has less than the preferred rest interval.",
                                "fixture_id": fixture.id,
                                "related_fixture_id": other_fixture.id,
                            }
                        )
                team_windows.setdefault(team.id, []).append((fixture, slot))
        stale = sorted(set(assignment_map) - set(fixture_by_id))
        for fixture_id in stale:
            errors.append(
                {
                    "code": "fixture_outside_calendar_plan",
                    "message": "An assigned fixture is no longer included in the calendar plan.",
                    "fixture_id": fixture_id,
                }
            )
        missing = sorted(set(fixture_by_id) - set(assignment_map))
        return {
            "valid": not errors and not missing,
            "errors": errors,
            "warnings": warnings,
            "unassigned_fixture_ids": missing,
        }
