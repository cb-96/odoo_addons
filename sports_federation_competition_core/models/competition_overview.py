from odoo import _, api, fields, models


class FederationCompetitionEdition(models.Model):
    _inherit = "federation.competition.edition"

    role_assignment_count = fields.Integer(compute="_compute_v2_core_counts")
    event_count = fields.Integer(compute="_compute_v2_core_counts")
    workflow_progress = fields.Integer(compute="_compute_workflow_progress")
    workflow_next_action = fields.Char(compute="_compute_workflow_progress")

    @api.depends("role_assignment_ids", "event_ids", "engine_state")
    def _compute_v2_core_counts(self):
        for rec in self:
            rec.role_assignment_count = len(rec.role_assignment_ids)
            rec.event_count = len(rec.event_ids)

    def _workflow_steps(self):
        self.ensure_one()
        steps = [bool(self.tournament_ids), bool(self.role_assignment_ids)]
        optional_fields = (
            "registration_window_ids",
            "structure_ids",
            "matchday_ids",
            "schedule_ids",
            "publication_ids",
        )
        steps.extend(
            bool(self[field]) if field in self._fields else False
            for field in optional_fields
        )
        return steps

    @api.depends("tournament_ids", "role_assignment_ids", "engine_state")
    def _compute_workflow_progress(self):
        for rec in self:
            steps = rec._workflow_steps()
            rec.workflow_progress = round(100 * sum(steps) / len(steps)) if steps else 0
            if not rec.tournament_ids:
                rec.workflow_next_action = _("Add at least one division")
            elif not rec.role_assignment_ids:
                rec.workflow_next_action = _("Assign responsible users")
            elif (
                "registration_window_ids" in rec._fields
                and not rec.registration_window_ids
            ):
                rec.workflow_next_action = _("Create registration windows")
            elif "structure_ids" in rec._fields and not rec.structure_ids:
                rec.workflow_next_action = _("Finalize registrations and build formats")
            elif "matchday_ids" in rec._fields and not rec.matchday_ids:
                rec.workflow_next_action = _("Create match days and capacity")
            elif "schedule_ids" in rec._fields and not rec.schedule_ids:
                rec.workflow_next_action = _("Create working schedules")
            elif "publication_ids" in rec._fields and not rec.publication_ids:
                rec.workflow_next_action = _("Review and publish schedules")
            else:
                rec.workflow_next_action = _("Monitor competition operations")

    def action_v2_role_assignments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Responsibilities"),
            "res_model": "federation.competition.role.assignment",
            "view_mode": "list,form",
            "domain": [("edition_id", "=", self.id)],
            "context": {"default_edition_id": self.id},
        }

    def action_v2_events(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Competition history"),
            "res_model": "federation.competition.event",
            "view_mode": "list,form",
            "domain": [("edition_id", "=", self.id)],
        }
