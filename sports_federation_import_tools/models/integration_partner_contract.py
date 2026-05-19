from odoo import fields, models


class FederationIntegrationPartnerContract(models.Model):
    _name = "federation.integration.partner.contract"
    _description = "Federation Integration Partner Contract"
    _order = "partner_id, contract_id"

    STATE_SELECTION = [
        ("active", "Active"),
        ("suspended", "Suspended"),
        ("deprecated", "Deprecated"),
    ]

    partner_id = fields.Many2one(
        "federation.integration.partner",
        required=True,
        ondelete="cascade",
    )
    contract_id = fields.Many2one(
        "federation.integration.contract",
        required=True,
        ondelete="cascade",
    )
    state = fields.Selection(STATE_SELECTION, required=True, default="active")
    notes = fields.Text()
    last_used_on = fields.Datetime(readonly=True)
    direction = fields.Selection(related="contract_id.direction", readonly=True)
    version = fields.Char(related="contract_id.version", readonly=True)
    route_hint = fields.Char(related="contract_id.route_hint", readonly=True)

    _partner_contract_unique = models.Constraint(
        "UNIQUE(partner_id, contract_id)",
        "A partner can only subscribe to a contract once.",
    )

    def mark_used(self):
        """Handle mark used."""
        self.write({"last_used_on": fields.Datetime.now()})
