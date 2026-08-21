from odoo import api, models


class FederationScheduleValidator(models.AbstractModel):
    _name = "federation.schedule.validator"
    _description = "Pure Schedule Validator"

    @api.model
    def validate_map(self, schedule, assignment_map):
        errors = []
        warnings = []
        windows = {}
        fixture_by_id = {
            f.id: f for f in schedule.matchday_id.allocation_ids.mapped("fixture_ids")
        }
        slot_by_id = {s.id: s for s in schedule.matchday_id.slot_ids}
        used_slots = set()
        for fixture_id, slot_id in assignment_map.items():
            fixture = fixture_by_id.get(fixture_id)
            slot = slot_by_id.get(slot_id)
            if not fixture or not slot:
                errors.append(
                    {
                        "code": "scope",
                        "message": "Fixture or slot is outside this schedule.",
                    }
                )
                continue
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
            for team in (fixture.home_team_id, fixture.away_team_id):
                if not team:
                    continue
                for other_fixture, other_slot in windows.get(team.id, []):
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
                windows.setdefault(team.id, []).append((fixture, slot))
        required = set(fixture_by_id)
        missing = sorted(required - set(assignment_map))
        return {
            "valid": not errors and not missing,
            "errors": errors,
            "warnings": warnings,
            "unassigned_fixture_ids": missing,
        }
