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
            if not fixture._is_schedulable():
                errors.append(
                    {
                        "code": "participants_unresolved",
                        "message": "Resolve both fixture participants, or link them to an earlier match or stage ranking, before scheduling.",
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
        # A follow-up match must start after the match that decides its teams.
        for fixture_id, slot_id in assignment_map.items():
            fixture, slot = fixture_by_id.get(fixture_id), slot_by_id.get(slot_id)
            if not fixture or not slot:
                continue
            for source in (
                fixture.home_source_fixture_id,
                fixture.away_source_fixture_id,
            ):
                source_slot = (
                    slot_by_id.get(assignment_map.get(source.id)) if source else None
                )
                if source_slot and source_slot.end_datetime > slot.start_datetime:
                    errors.append(
                        {
                            "code": "placeholder_before_source",
                            "message": f"{fixture.name} starts before {source.name} ends; it depends on that result.",
                            "fixture_id": fixture.id,
                            "related_fixture_id": source.id,
                        }
                    )
        errors.extend(
            self._stage_order_errors(
                schedule, assignment_map, fixture_by_id, slot_by_id
            )
        )
        stale = sorted(set(assignment_map) - set(fixture_by_id))
        for fixture_id in stale:
            errors.append(
                {
                    "code": "fixture_outside_calendar_plan",
                    "message": "An assigned fixture is no longer included in the calendar plan.",
                    "fixture_id": fixture_id,
                }
            )
        # Fixtures that can never be played here (a future bye has no
        # opponent and no source) are not counted as unassigned.
        missing = sorted(
            fixture_id
            for fixture_id, fixture in fixture_by_id.items()
            if fixture_id not in assignment_map
            and (
                (fixture.home_team_id and fixture.away_team_id)
                or fixture._is_schedulable()
            )
        )
        return {
            "valid": not errors and not missing,
            "errors": errors,
            "warnings": warnings,
            "unassigned_fixture_ids": missing,
        }

    @api.model
    def _stage_order_errors(self, schedule, assignment_map, fixture_by_id, slot_by_id):
        """Stage game days and stage chronology.

        * A stage limited to some game days cannot be planned on another day.
        * A stage fed by earlier stages (knockout after groups) starts after
          every match of those stages on the same day has ended, and is not
          planned on a day before one of their matches.
        """
        errors = []
        day = schedule.matchday_id
        planned = [
            (fixture_by_id[fixture_id], slot_by_id[slot_id])
            for fixture_id, slot_id in assignment_map.items()
            if fixture_id in fixture_by_id and slot_id in slot_by_id
        ]
        if not planned:
            return errors
        stage_end = {}
        for fixture, slot in planned:
            current = stage_end.get(fixture.stage_id.id)
            if current is None or slot.end_datetime > current[0]:
                stage_end[fixture.stage_id.id] = (slot.end_datetime, fixture)
        later_stage_ids = None
        for fixture, slot in planned:
            stage = fixture.stage_id
            windows = stage.matchday_ids if "matchday_ids" in stage._fields else False
            if windows and day not in windows:
                errors.append(
                    {
                        "code": "stage_game_day",
                        "message": f"{stage.display_name} is not planned on {day.display_name}. Choose one of its game days or change the stage game days.",
                        "fixture_id": fixture.id,
                    }
                )
            sources = stage._planning_source_stages()
            if not sources:
                continue
            for source in sources:
                end = stage_end.get(source.id)
                if end and end[0] > slot.start_datetime:
                    errors.append(
                        {
                            "code": "stage_before_source",
                            "message": f"{fixture.name} starts before {source.display_name} ends; its teams come from that table.",
                            "fixture_id": fixture.id,
                            "related_fixture_id": end[1].id,
                        }
                    )
            if later_stage_ids is None:
                later_stage_ids = self._stage_ids_on_later_days(day)
            late = sources.filtered(lambda source: source.id in later_stage_ids)
            if late:
                errors.append(
                    {
                        "code": "stage_before_source",
                        "message": f"{fixture.name} is planned before {', '.join(late.mapped('display_name'))} has finished on a later game day.",
                        "fixture_id": fixture.id,
                    }
                )
        return errors

    @api.model
    def _stage_ids_on_later_days(self, day):
        if not day.edition_id or not day.date:
            return set()
        later = self.env["federation.matchday"].search(
            [("edition_id", "=", day.edition_id.id), ("date", ">", day.date)]
        )
        return set(later.mapped("allocation_ids.fixture_ids.stage_id").ids)
