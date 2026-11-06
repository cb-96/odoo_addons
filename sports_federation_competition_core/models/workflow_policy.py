from odoo import api, fields, models


class FederationCompetitionEditionWorkflowPolicy(models.Model):
    _inherit = "federation.competition.edition"

    workflow_mode = fields.Selection(
        [
            ("simple", "Streamlined"),
            ("controlled", "Independent Review"),
            ("custom", "Advanced / Custom"),
        ],
        default="simple",
        required=True,
        tracking=True,
    )
    registration_approval_required = fields.Boolean(default=False)
    structure_freeze_confirmation_required = fields.Boolean(default=False)
    schedule_approval_required = fields.Boolean(default=False)
    schedule_self_approval_allowed = fields.Boolean(default=True)
    schedule_auto_publish_after_approval = fields.Boolean(default=True)
    result_verification_required = fields.Boolean(default=False)
    result_approval_required = fields.Boolean(default=False)
    result_self_verification_allowed = fields.Boolean(default=True)
    result_self_approval_allowed = fields.Boolean(default=True)
    standings_freeze_confirmation_required = fields.Boolean(default=False)
    auto_recompute_standings = fields.Boolean(default=True)
    auto_progress_completed_stage = fields.Boolean(default=True)
    roster_approval_required = fields.Boolean(default=False)
    match_sheet_approval_required = fields.Boolean(default=False)

    @api.onchange("workflow_mode")
    def _onchange_workflow_mode(self):
        for edition in self:
            if edition.workflow_mode == "simple":
                edition.update(edition._workflow_policy_values("simple"))
            elif edition.workflow_mode == "controlled":
                edition.update(edition._workflow_policy_values("controlled"))

    def write(self, values):
        mode = values.get("workflow_mode")
        if mode in ("simple", "controlled"):
            values = dict(values, **self._workflow_policy_values(mode))
        return super().write(values)

    @api.model
    def _workflow_policy_values(self, mode):
        strict = mode == "controlled"
        return {
            "registration_approval_required": strict,
            "structure_freeze_confirmation_required": strict,
            "schedule_approval_required": strict,
            "schedule_self_approval_allowed": not strict,
            "schedule_auto_publish_after_approval": not strict,
            "result_verification_required": strict,
            "result_approval_required": strict,
            "result_self_verification_allowed": not strict,
            "result_self_approval_allowed": not strict,
            "standings_freeze_confirmation_required": strict,
            "auto_recompute_standings": True,
            "auto_progress_completed_stage": not strict,
            "roster_approval_required": strict,
            "match_sheet_approval_required": strict,
        }

    def workflow_requires(self, approval):
        self.ensure_one()
        return bool(getattr(self, approval))
