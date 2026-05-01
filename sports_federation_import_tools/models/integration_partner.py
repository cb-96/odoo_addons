from odoo import api, fields, models
from odoo.exceptions import AccessError


class FederationIntegrationPartner(models.Model):
    _name = "federation.integration.partner"
    _description = "Federation Integration Partner"
    _order = "name"
    _inherit = [
        "federation.integration.partner.token.mixin",
        "federation.integration.partner.rotation.mixin",
    ]

    TOKEN_HASH_PREFIX = "pbkdf2_sha256"
    TOKEN_HASH_ROUNDS = 390000
    TOKEN_SALT_BYTES = 16

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    contact_partner_id = fields.Many2one("res.partner", ondelete="set null")
    auth_token = fields.Char(copy=False, readonly=True)
    auth_token_last4 = fields.Char(readonly=True, copy=False)
    token_last_rotated_on = fields.Datetime(readonly=True)
    token_rotation_required = fields.Boolean(readonly=True, default=False, copy=False)
    last_request_on = fields.Datetime(readonly=True)
    active = fields.Boolean(default=True)
    notes = fields.Text()
    subscription_ids = fields.One2many(
        "federation.integration.partner.contract",
        "partner_id",
    )
    delivery_ids = fields.One2many(
        "federation.integration.delivery",
        "partner_id",
    )

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Integration partner codes must be unique.",
    )

    def _register_hook(self):
        """Migrate legacy plaintext tokens into hashed storage."""
        result = super()._register_hook()
        self._migrate_plaintext_tokens()
        return result

    def _get_subscription(self, contract_code):
        """Return subscription."""
        self.ensure_one()
        return self.subscription_ids.filtered(
            lambda line: line.contract_id.code == contract_code
            and line.state == "active"
        )[:1]

    @api.model
    def authenticate_partner(self, partner_code, token, contract_code=None):
        """Handle authenticate partner."""
        partner = self.sudo().search(
            [
                ("code", "=", partner_code),
                ("active", "=", True),
            ],
            limit=1,
        )
        if not partner or not partner._verify_stored_auth_token(
            partner.auth_token, token
        ):
            raise AccessError("Invalid partner credentials.")

        partner.write({"last_request_on": fields.Datetime.now()})
        subscription = False
        if contract_code:
            subscription = partner._get_subscription(contract_code)
            if not subscription:
                raise AccessError("The partner is not subscribed to this contract.")
            subscription.mark_used()
        return partner, subscription
