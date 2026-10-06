from odoo import api, fields, models


class FederationCreateCompetitionWizardJourney(models.TransientModel):
    _inherit = "federation.create.competition.wizard"

    setup_template = fields.Selection(
        selection_add=[("custom", "Custom")],
        string="Competition Type",
        ondelete={"custom": "set default"},
    )
    workflow_mode = fields.Selection(
        [("simple", "Simple"), ("controlled", "Controlled"), ("custom", "Custom")],
        default="simple",
        required=True,
        string="Workflow",
    )
    workflow_summary = fields.Text(compute="_compute_workflow_summary", readonly=True)
    default_venue_id = fields.Many2one("federation.venue", string="Default Venue")

    @api.depends("workflow_mode")
    def _compute_workflow_summary(self):
        summaries = {
            "simple": (
                "Minimal handoffs for small competitions. Schedule review and result "
                "checks follow the streamlined policy while validation and audit "
                "history remain active."
            ),
            "controlled": (
                "Separate people plan and approve schedules and results. Use this when "
                "independent review and clear handoffs are required."
            ),
            "custom": (
                "Create the competition first, then choose each schedule, result, "
                "self-approval, publication, and standings checkpoint on Competition details."
            ),
        }
        for wizard in self:
            wizard.workflow_summary = summaries.get(wizard.workflow_mode, "")

    def action_create_competition(self):
        self.ensure_one()
        action = super().action_create_competition()
        edition = self.env["federation.competition.edition"].browse(action.get("res_id")).exists()
        if edition:
            edition.write({"workflow_mode": self.workflow_mode})
            action = edition.action_open_competition_planner()
            action["context"] = dict(
                self.env.context,
                competition_setup_created=True,
                default_edition_id=edition.id,
                default_venue_id=self.default_venue_id.id,
            )
        return action
