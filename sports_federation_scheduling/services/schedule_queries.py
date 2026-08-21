from odoo import api, models


class FederationScheduleQueries(models.AbstractModel):
    _name = "federation.schedule.queries"
    _description = "Schedule Query Service"

    @api.model
    def load(self, schedule_id):
        s = self.env["federation.schedule"].browse(int(schedule_id)).exists()
        assignments = {a.fixture_id.id: a for a in s.assignment_ids}
        fixtures = s.matchday_id.allocation_ids.mapped("fixture_ids")
        return {
            "schedule": {
                "id": s.id,
                "name": s.name,
                "state": s.state,
                "revision": s.revision,
            },
            "matchday": {"id": s.matchday_id.id, "name": s.matchday_id.name},
            "assignments": [
                {
                    "id": a.id,
                    "fixture_id": a.fixture_id.id,
                    "fixture_name": a.fixture_id.name,
                    "slot_id": a.slot_id.id,
                }
                for a in s.assignment_ids
            ],
            "unassigned": [
                {"id": f.id, "name": f.name, "round_number": f.round_number}
                for f in fixtures
                if f.id not in assignments
            ],
            "slots": [
                {
                    "id": slot.id,
                    "court_id": slot.court_id.id,
                    "court_name": slot.court_id.display_name,
                    "start": slot.start_datetime,
                    "end": slot.end_datetime,
                    "state": slot.state,
                }
                for slot in s.matchday_id.slot_ids
            ],
        }

    @api.model
    def delta(self, schedule, changed):
        schedule.invalidate_recordset(["revision"])
        return {
            "schedule_id": schedule.id,
            "revision": schedule.revision,
            "changed_assignments": [
                {"id": a.id, "fixture_id": a.fixture_id.id, "slot_id": a.slot_id.id}
                for a in changed
            ],
            "validation": self.env["federation.schedule.validator"].validate_map(
                schedule,
                {a.fixture_id.id: a.slot_id.id for a in schedule.assignment_ids},
            ),
        }
