from odoo import api, models


class FederationDeterministicSolver(models.AbstractModel):
    _name = "federation.schedule.solver"
    _description = "Deterministic Side-Effect-Free Schedule Solver"

    @api.model
    def propose(self, schedule):
        current = {a.fixture_id.id: a.slot_id.id for a in schedule.assignment_ids}
        validator = self.env["federation.schedule.validator"]
        fixtures = (
            schedule.matchday_id.allocation_ids.mapped("fixture_ids")
            .filtered(lambda f: f.id not in current)
            .sorted(lambda f: (f.round_number, f.sequence, f.id))
        )
        slots = schedule.matchday_id.slot_ids.filtered(
            lambda s: s.state == "available" and s.id not in current.values()
        ).sorted(lambda s: (s.start_datetime, s.court_id.id, s.id))
        assignments = []
        for fixture in fixtures:
            best = False
            for slot in slots:
                candidate = {**current, fixture.id: slot.id}
                result = validator.validate_map(schedule, candidate)
                if not result["errors"]:
                    best = slot
                    break
            if best:
                current[fixture.id] = best.id
                slots -= best
                assignments.append({"fixture_id": fixture.id, "slot_id": best.id})
        validation = validator.validate_map(schedule, current)
        return {
            "assignments": assignments,
            "unassigned_fixture_ids": validation["unassigned_fixture_ids"],
            "validation": validation,
        }
