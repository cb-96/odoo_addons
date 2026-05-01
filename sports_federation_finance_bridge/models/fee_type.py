from odoo import fields, models


class FederationFeeType(models.Model):
    _name = "federation.fee.type"
    _description = "Federation Fee Type"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    category = fields.Selection(
        [
            ("registration", "Registration"),
            ("license", "License"),
            ("fine", "Fine"),
            ("reimbursement", "Reimbursement"),
            ("other", "Other"),
        ],
        required=True,
    )
    default_amount = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _code_unique = models.Constraint("unique (code)", "Fee type code must be unique.")
