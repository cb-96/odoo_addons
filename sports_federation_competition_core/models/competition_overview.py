from odoo import _, api, fields, models


class FederationCompetitionEdition(models.Model):
    _inherit = "federation.competition.edition"

    role_assignment_count = fields.Integer(compute="_compute_core_counts")
    event_count = fields.Integer(compute="_compute_core_counts")
    workflow_progress = fields.Integer(compute="_compute_workflow_progress")
    workflow_next_action = fields.Char(compute="_compute_workflow_progress")
    journey_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("ready", "Ready"),
            ("live", "Live"),
            ("finished", "Finished"),
        ],
        compute="_compute_workflow_progress",
        string="Journey Status",
    )
    journey_blocker_count = fields.Integer(compute="_compute_workflow_progress")

    @api.depends("role_assignment_ids", "event_ids", "state")
    def _compute_core_counts(self):
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

    @api.depends("tournament_ids", "role_assignment_ids", "state")
    def _compute_workflow_progress(self):
        for rec in self:
            steps = rec._workflow_steps()
            rec.workflow_progress = round(100 * sum(steps) / len(steps)) if steps else 0
            rec.journey_blocker_count = len([step for step in steps if not step])
            rec.journey_state = (
                "finished"
                if rec.state in ("closed", "cancelled")
                else (
                    "live"
                    if "publication_ids" in rec._fields and rec.publication_ids
                    else ("ready" if steps and all(steps[:-1]) else "draft")
                )
            )
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

    def action_role_assignments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Responsibilities"),
            "res_model": "federation.competition.role.assignment",
            "view_mode": "list,form",
            "domain": [("edition_id", "=", self.id)],
            "context": {"default_edition_id": self.id},
        }

    def action_competition_events(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Competition history"),
            "res_model": "federation.competition.event",
            "view_mode": "list,form",
            "domain": [("edition_id", "=", self.id)],
        }

    def action_open_next_workspace(self):
        self.ensure_one()
        candidates = (
            (
                not self.tournament_ids,
                "sports_federation_tournament.federation_tournament_action",
            ),
            (
                not self.role_assignment_ids,
                "sports_federation_competition_core.action_competition_roles_competition",
            ),
            (
                "registration_window_ids" in self._fields
                and not self.registration_window_ids,
                "sports_federation_registration.action_registration_desk",
            ),
            (
                "structure_ids" in self._fields and not self.structure_ids,
                "sports_federation_format.action_format_studio",
            ),
            (
                "matchday_ids" in self._fields and not self.matchday_ids,
                "sports_federation_calendar.action_calendar_planner",
            ),
            (
                "schedule_ids" in self._fields and not self.schedule_ids,
                "sports_federation_scheduling.action_schedule_planner_competition",
            ),
            (
                "publication_ids" in self._fields and not self.publication_ids,
                "sports_federation_schedule_approval.action_schedule_review_queue",
            ),
        )
        for needed, xmlid in candidates:
            if needed:
                return self.env["ir.actions.actions"]._for_xml_id(xmlid)
        return self.env["ir.actions.actions"]._for_xml_id(
            "sports_federation_matchday.action_matchday_control"
        )
