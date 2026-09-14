from odoo import _, fields, models


class FederationCompetitionEditionSetupEnhancements(models.Model):
    _inherit = "federation.competition.edition"

    setup_default_venue_id = fields.Many2one("federation.venue", string="Default Venue")

    def action_open_clone_setup(self):
        self.ensure_one()
        wizard = self.env["federation.competition.clone.setup.wizard"].create(
            {"source_edition_id": self.id}
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Copy Competition Setup"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }
