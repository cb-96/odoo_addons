from odoo import _, fields, models


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
    default_venue_id = fields.Many2one("federation.venue", string="Default Venue")

    def action_create_competition(self):
        self.ensure_one()
        action = super().action_create_competition()
        edition = self.env["federation.competition.edition"].browse(action.get("res_id")).exists()
        if edition:
            edition.write({"workflow_mode": self.workflow_mode})
            action = edition.get_formview_action()
            action["name"] = _("Continue Competition Setup")
            action["context"] = dict(
                self.env.context,
                competition_setup_created=True,
                default_edition_id=edition.id,
                default_venue_id=self.default_venue_id.id,
            )
        return action
