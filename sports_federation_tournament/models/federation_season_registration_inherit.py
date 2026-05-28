from odoo import api, fields, models


class FederationSeasonRegistration(models.Model):
    _inherit = "federation.season.registration"

    competition_id = fields.Many2one(
        "federation.competition",
        string="Competition",
        tracking=True,
        ondelete="set null",
        help="Competition this registration applies to.",
    )
    rule_set_id = fields.Many2one(
        "federation.rule.set",
        string="Rule Set",
        tracking=True,
        ondelete="set null",
        help="Competition rules for this registration. Auto-populated from competition if set.",
    )

    @api.onchange("competition_id")
    def _onchange_competition_id(self):
        """Handle onchange competition ID."""
        if self.competition_id and self.competition_id.rule_set_id:
            self.rule_set_id = self.competition_id.rule_set_id
