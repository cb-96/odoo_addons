from odoo import fields, models


class FederationIntegrationContract(models.Model):
    _name = "federation.integration.contract"
    _description = "Federation Integration Contract"
    _order = "direction, code"

    DIRECTION_SELECTION = [
        ("outbound", "Outbound"),
        ("inbound", "Inbound"),
    ]
    TRANSPORT_SELECTION = [
        ("json", "JSON"),
        ("csv", "CSV"),
        ("file", "File"),
    ]
    DEPRECATION_STAGE_SELECTION = [
        ("active", "Active"),
        ("deprecated", "Deprecated"),
        ("sunset", "Sunset"),
    ]

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    version = fields.Char(required=True)
    direction = fields.Selection(DIRECTION_SELECTION, required=True)
    transport = fields.Selection(TRANSPORT_SELECTION, required=True)
    route_hint = fields.Char()
    description = fields.Text()
    required_module = fields.Char(
        help="Optional module name that must be installed before this contract is operational.",
    )
    import_template_id = fields.Many2one(
        "federation.import.template",
        ondelete="set null",
    )
    deprecation_stage = fields.Selection(
        DEPRECATION_STAGE_SELECTION,
        required=True,
        default="active",
    )
    replacement_contract_id = fields.Many2one(
        "federation.integration.contract",
        ondelete="set null",
    )
    sunset_on = fields.Date()
    active = fields.Boolean(default=True)
    subscription_ids = fields.One2many(
        "federation.integration.partner.contract",
        "contract_id",
    )

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Integration contract codes must be unique.",
    )

    def _is_available(self):
        """Return whether the record is available."""
        self.ensure_one()
        if not self.required_module:
            return True
        return bool(
            self.env["ir.module.module"]
            .sudo()
            .search_count(
                [
                    ("name", "=", self.required_module),
                    ("state", "=", "installed"),
                ],
                limit=1,
            )
        )

    def build_manifest_payload(self, subscription=None):
        """Build manifest payload."""
        self.ensure_one()
        payload = {
            "code": self.code,
            "name": self.name,
            "version": self.version,
            "direction": self.direction,
            "transport": self.transport,
            "route_hint": self.route_hint,
            "description": self.description or "",
            "deprecation_stage": self.deprecation_stage,
            "sunset_on": (
                fields.Date.to_string(self.sunset_on) if self.sunset_on else None
            ),
            "replacement_contract": (
                self.replacement_contract_id.code
                if self.replacement_contract_id
                else None
            ),
            "available": self._is_available(),
        }
        if subscription:
            payload["subscription_state"] = subscription.state
            payload["last_used_on"] = (
                fields.Datetime.to_string(subscription.last_used_on)
                if subscription.last_used_on
                else None
            )
        return payload
