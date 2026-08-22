import json
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

class FederationScheduleAutoWizard(models.TransientModel):
    _name = "federation.schedule.auto.wizard"
    _description = "Fair Auto-Schedule Preview"
    schedule_id = fields.Many2one("federation.schedule", required=True, ondelete="cascade")
    same_club_weight = fields.Float(required=True)
    rest_weight = fields.Float(required=True)
    consecutive_weight = fields.Float(required=True)
    time_balance_weight = fields.Float(required=True)
    court_balance_weight = fields.Float(required=True)
    preferred_rest_minutes = fields.Integer(required=True)
    max_consecutive_games = fields.Integer(required=True)
    replace_automatic_assignments = fields.Boolean(default=False)
    preview_ready = fields.Boolean(readonly=True)
    proposed_count = fields.Integer(readonly=True)
    unassigned_count = fields.Integer(readonly=True)
    fairness_score = fields.Float(readonly=True)
    preview_report = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            schedule = self.env["federation.schedule"].browse(vals.get("schedule_id"))
            vals.setdefault("same_club_weight", schedule.fairness_same_club_weight)
            vals.setdefault("rest_weight", schedule.fairness_rest_weight)
            vals.setdefault("consecutive_weight", schedule.fairness_consecutive_weight)
            vals.setdefault("time_balance_weight", schedule.fairness_time_balance_weight)
            vals.setdefault("court_balance_weight", schedule.fairness_court_balance_weight)
            vals.setdefault("preferred_rest_minutes", schedule.preferred_rest_minutes)
            vals.setdefault("max_consecutive_games", schedule.max_consecutive_games)
        return super().create(vals_list)

    def _configuration(self):
        self.ensure_one()
        if min(self.same_club_weight, self.rest_weight, self.consecutive_weight,
               self.time_balance_weight, self.court_balance_weight) < 0:
            raise ValidationError(_("Fairness weights cannot be negative."))
        if self.preferred_rest_minutes < 0 or self.max_consecutive_games < 1:
            raise ValidationError(_("Enter a valid rest target and consecutive-game limit."))
        return {
            "same_club_weight": self.same_club_weight,
            "rest_weight": self.rest_weight,
            "consecutive_weight": self.consecutive_weight,
            "time_balance_weight": self.time_balance_weight,
            "court_balance_weight": self.court_balance_weight,
            "preferred_rest_minutes": self.preferred_rest_minutes,
            "max_consecutive_games": self.max_consecutive_games,
        }

    def action_preview(self):
        self.ensure_one()
        proposal = self.env["federation.schedule.fairness.solver"].propose(
            self.schedule_id, self._configuration(), self.replace_automatic_assignments
        )
        report = proposal["fairness"]
        self.write({
            "preview_ready": True,
            "proposed_count": len(proposal["assignments"]),
            "unassigned_count": len(proposal["unassigned_fixture_ids"]),
            "fairness_score": report["weighted_score"],
            "preview_report": json.dumps(report, indent=2, sort_keys=True),
        })
        return {
            "type": "ir.actions.act_window", "res_model": self._name,
            "res_id": self.id, "view_mode": "form", "target": "new",
        }

    def action_apply(self):
        self.ensure_one()
        schedule = self.schedule_id
        self.env["federation.competition.role.assignment"].assert_role(
            schedule.edition_id, "schedule_planner", "competition_director"
        )
        proposal = self.env["federation.schedule.fairness.solver"].propose(
            schedule, self._configuration(), self.replace_automatic_assignments
        )
        if not proposal["assignments"]:
            raise ValidationError(_("The solver found no assignments to apply."))
        expected_revision = schedule.revision
        self.env.cr.execute(
            "UPDATE federation_schedule SET revision=revision+1 WHERE id=%s AND revision=%s RETURNING revision",
            (schedule.id, expected_revision),
        )
        row = self.env.cr.fetchone()
        if not row:
            raise ValidationError(_("The schedule changed in another session. Reopen the preview."))
        new_revision = row[0]
        if self.replace_automatic_assignments:
            schedule.assignment_ids.filtered(lambda a: a.method == "automatic").unlink()
        existing = {a.fixture_id.id: a for a in schedule.assignment_ids}
        created = self.env["federation.schedule.assignment"]
        for item in proposal["assignments"]:
            assignment = existing.get(item["fixture_id"])
            if assignment:
                old_slot = assignment.slot_id
                assignment.write({"slot_id": item["slot_id"], "method": "automatic"})
            else:
                old_slot = self.env["federation.schedule.slot"]
                assignment = self.env["federation.schedule.assignment"].create({
                    "schedule_id": schedule.id, "fixture_id": item["fixture_id"],
                    "slot_id": item["slot_id"], "method": "automatic",
                })
                created |= assignment
            self.env["federation.schedule.change"].create({
                "schedule_id": schedule.id, "revision": new_revision,
                "command": "fair_auto_schedule", "fixture_id": item["fixture_id"],
                "old_slot_id": old_slot.id, "new_slot_id": item["slot_id"],
                "reason": _("Weighted fairness auto-schedule"),
            })
        schedule.write({
            "fairness_same_club_weight": self.same_club_weight,
            "fairness_rest_weight": self.rest_weight,
            "fairness_consecutive_weight": self.consecutive_weight,
            "fairness_time_balance_weight": self.time_balance_weight,
            "fairness_court_balance_weight": self.court_balance_weight,
            "preferred_rest_minutes": self.preferred_rest_minutes,
            "max_consecutive_games": self.max_consecutive_games,
            "fairness_last_score": proposal["fairness"]["weighted_score"],
            "fairness_last_report": proposal["fairness"],
        })
        return {"type": "ir.actions.act_window_close"}
