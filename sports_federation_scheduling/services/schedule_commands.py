from odoo import _, api, models
from odoo.exceptions import ValidationError


class FederationScheduleCommands(models.AbstractModel):
    _name = "federation.schedule.commands"
    _description = "Schedule Command Service"

    def _find_replay(self, schedule_id, idempotency_key):
        if not idempotency_key:
            return False
        return self.env["federation.schedule.change"].search(
            [
                ("schedule_id", "=", int(schedule_id)),
                ("idempotency_key", "=", idempotency_key),
            ],
            limit=1,
        )

    def _resolve(self, schedule_id, expected_revision):
        schedule = self.env["federation.schedule"].browse(int(schedule_id)).exists()
        if not schedule:
            raise ValidationError(_("The schedule no longer exists."))
        self.env["federation.competition.role.assignment"].assert_role(
            schedule.edition_id, "schedule_planner", "competition_director"
        )
        schedule.assert_mutable()
        self.env.cr.execute(
            "UPDATE federation_schedule SET revision=revision+1 WHERE id=%s AND revision=%s RETURNING revision",
            (schedule.id, int(expected_revision)),
        )
        row = self.env.cr.fetchone()
        if not row:
            raise ValidationError(
                _("The schedule changed in another session. Refresh and retry.")
            )
        schedule.invalidate_recordset(["revision"])
        return schedule, row[0]

    def _map(self, schedule):
        return {a.fixture_id.id: a.slot_id.id for a in schedule.assignment_ids}

    @api.model
    def assign(
        self,
        schedule_id,
        fixture_id,
        slot_id,
        expected_revision,
        reason=False,
        idempotency_key=False,
    ):
        replay = self._find_replay(schedule_id, idempotency_key)
        if replay:
            return self.env["federation.schedule.queries"].delta(replay.schedule_id, [])
        schedule, new_revision = self._resolve(schedule_id, expected_revision)
        fixture = self.env["federation.fixture"].browse(int(fixture_id)).exists()
        slot = self.env["federation.schedule.slot"].browse(int(slot_id)).exists()
        candidate = self._map(schedule)
        candidate[fixture.id] = slot.id
        validation = self.env["federation.schedule.validator"].validate_map(
            schedule, candidate
        )
        if validation["errors"]:
            raise ValidationError(validation["errors"][0]["message"])
        assignment = schedule.assignment_ids.filtered(
            lambda a: a.fixture_id == fixture
        )[:1]
        old = assignment.slot_id
        if assignment:
            assignment.write({"slot_id": slot.id, "method": "manual"})
        else:
            assignment = self.env["federation.schedule.assignment"].create(
                {
                    "schedule_id": schedule.id,
                    "fixture_id": fixture.id,
                    "slot_id": slot.id,
                    "method": "manual",
                }
            )
        self.env["federation.schedule.change"].create(
            {
                "schedule_id": schedule.id,
                "revision": new_revision,
                "command": "assign",
                "fixture_id": fixture.id,
                "old_slot_id": old.id if old else False,
                "new_slot_id": slot.id,
                "reason": reason,
                "idempotency_key": idempotency_key,
            }
        )
        return self.env["federation.schedule.queries"].delta(schedule, assignment)

    @api.model
    def unassign(
        self,
        schedule_id,
        fixture_id,
        expected_revision,
        reason=False,
        idempotency_key=False,
    ):
        replay = self._find_replay(schedule_id, idempotency_key)
        if replay:
            return self.env["federation.schedule.queries"].delta(replay.schedule_id, [])
        schedule, new_revision = self._resolve(schedule_id, expected_revision)
        assignment = schedule.assignment_ids.filtered(
            lambda a: a.fixture_id.id == int(fixture_id)
        )[:1]
        if not assignment:
            return self.env["federation.schedule.queries"].delta(schedule, [])
        old = assignment.slot_id
        fixture = assignment.fixture_id
        assignment.unlink()
        self.env["federation.schedule.change"].create(
            {
                "schedule_id": schedule.id,
                "revision": new_revision,
                "command": "unassign",
                "fixture_id": fixture.id,
                "old_slot_id": old.id,
                "reason": reason,
                "idempotency_key": idempotency_key,
            }
        )
        return self.env["federation.schedule.queries"].delta(schedule, [])

    @api.model
    def apply_proposal(self, schedule_id, expected_revision):
        schedule, new_revision = self._resolve(schedule_id, expected_revision)
        proposal = self.env["federation.schedule.solver"].propose(schedule)
        created = (
            self.env["federation.schedule.assignment"].create(
                [
                    {
                        "schedule_id": schedule.id,
                        "fixture_id": x["fixture_id"],
                        "slot_id": x["slot_id"],
                        "method": "automatic",
                    }
                    for x in proposal["assignments"]
                ]
            )
            if proposal["assignments"]
            else self.env["federation.schedule.assignment"]
        )
        for a in created:
            self.env["federation.schedule.change"].create(
                {
                    "schedule_id": schedule.id,
                    "revision": new_revision,
                    "command": "auto_assign",
                    "fixture_id": a.fixture_id.id,
                    "new_slot_id": a.slot_id.id,
                }
            )
        return self.env["federation.schedule.queries"].delta(schedule, created)

    @api.model
    def submit(self, schedule_id, expected_revision, warning_override_reason=False):
        schedule, new_revision = self._resolve(schedule_id, expected_revision)
        validation = self.env["federation.schedule.validator"].validate_map(
            schedule, self._map(schedule)
        )
        if not validation["valid"]:
            raise ValidationError(
                _("Resolve all errors and unassigned fixtures before submitting.")
            )
        if validation["warnings"] and not (warning_override_reason or "").strip():
            raise ValidationError(
                _("Provide a manager reason to accept schedule warnings.")
            )
        if validation["warnings"]:
            self.env["federation.schedule.change"].create(
                {
                    "schedule_id": schedule.id,
                    "revision": new_revision,
                    "command": "warning_override",
                    "reason": warning_override_reason,
                }
            )
        schedule.state = "ready_for_review"
        self.env["federation.competition.event"].emit(
            schedule, "schedule_submitted", {"revision": new_revision}
        )
        return {
            "schedule_id": schedule.id,
            "revision": new_revision,
            "state": schedule.state,
        }
