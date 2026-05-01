from odoo import fields, models


class FederationIntegrationPartnerTokenWizard(models.TransientModel):
    _name = "federation.integration.partner.token.wizard"
    _description = "Federation Integration Partner Token Wizard"

    partner_id = fields.Many2one(
        "federation.integration.partner",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    issued_token = fields.Char(required=True, readonly=True)
    token_last_rotated_on = fields.Datetime(
        related="partner_id.token_last_rotated_on",
        readonly=True,
    )
