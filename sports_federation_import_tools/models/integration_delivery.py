from odoo import api, fields, models
from odoo.addons.sports_federation_base.models.failure_feedback import (
    FAILURE_CATEGORY_SELECTION,
)
from odoo.addons.sports_federation_import_tools.workflow_states import (
    INBOUND_DELIVERY_ACTIVE_STATES,
    INBOUND_DELIVERY_STATE_CANCELLED,
    INBOUND_DELIVERY_STATE_FAILED,
    INBOUND_DELIVERY_STATE_PROCESSED,
    INBOUND_DELIVERY_STATE_PROCESSED_WITH_ERRORS,
    INBOUND_DELIVERY_STATE_SELECTION,
    INBOUND_DELIVERY_STATE_STAGED,
)
from odoo.exceptions import ValidationError


class FederationIntegrationDelivery(models.Model):
    _name = "federation.integration.delivery"
    _description = "Federation Integration Delivery"
    _order = "received_on desc, id desc"
    _inherit = [
        "federation.integration.delivery.stage.mixin",
        "federation.integration.delivery.workflow.mixin",
        "federation.integration.delivery.retention.mixin",
    ]
    ACTIVE_DEDUPLICATION_STATES = INBOUND_DELIVERY_ACTIVE_STATES

    RETENTION_DAYS_BY_STATE = {
        INBOUND_DELIVERY_STATE_PROCESSED: 180,
        INBOUND_DELIVERY_STATE_PROCESSED_WITH_ERRORS: 180,
        INBOUND_DELIVERY_STATE_FAILED: 365,
        INBOUND_DELIVERY_STATE_CANCELLED: 90,
    }

    STATE_SELECTION = INBOUND_DELIVERY_STATE_SELECTION

    RECEIVED_VIA_SELECTION = [
        ("api", "Partner API"),
        ("manual", "Manual"),
    ]

    name = fields.Char(compute="_compute_name", store=True)
    partner_id = fields.Many2one(
        "federation.integration.partner",
        required=True,
        ondelete="restrict",
    )
    contract_id = fields.Many2one(
        "federation.integration.contract",
        required=True,
        ondelete="restrict",
    )
    import_template_id = fields.Many2one(
        "federation.import.template",
        related="contract_id.import_template_id",
        store=True,
        readonly=True,
    )
    governance_job_id = fields.Many2one(
        "federation.import.job",
        ondelete="set null",
        readonly=True,
    )
    attachment_id = fields.Many2one(
        "ir.attachment",
        ondelete="set null",
        readonly=True,
    )
    filename = fields.Char(required=True)
    payload_checksum = fields.Char(required=True, readonly=True)
    idempotency_key = fields.Char(readonly=True)
    idempotency_fingerprint = fields.Char(readonly=True)
    source_reference = fields.Char()
    state = fields.Selection(
        STATE_SELECTION,
        required=True,
        default=INBOUND_DELIVERY_STATE_STAGED,
        readonly=True,
    )
    received_via = fields.Selection(
        RECEIVED_VIA_SELECTION, required=True, default="api"
    )
    received_on = fields.Datetime(
        required=True, default=fields.Datetime.now, readonly=True
    )
    previewed_on = fields.Datetime(readonly=True)
    approved_on = fields.Datetime(readonly=True)
    processed_on = fields.Datetime(readonly=True)
    line_count = fields.Integer(readonly=True)
    success_count = fields.Integer(readonly=True)
    error_count = fields.Integer(readonly=True)
    failure_category = fields.Selection(FAILURE_CATEGORY_SELECTION, readonly=True)
    operator_message = fields.Text(readonly=True)
    result_message = fields.Text(readonly=True)
    verification_summary = fields.Text(readonly=True)
    notes = fields.Text()

    _partner_contract_idempotency_key_unique = models.Constraint(
        "UNIQUE(partner_id, contract_id, idempotency_key)",
        "This partner contract already uses that inbound idempotency key.",
    )

    @api.depends("partner_id", "contract_id", "filename")
    def _compute_name(self):
        """Compute name."""
        for record in self:
            parts = [
                record.partner_id.name or "Partner",
                record.contract_id.code or "contract",
                record.filename or "delivery",
            ]
            record.name = " - ".join(parts)

    @api.constrains("contract_id")
    def _check_contract_direction(self):
        """Validate contract direction."""
        for record in self:
            if record.contract_id.direction != "inbound":
                raise ValidationError(
                    "Only inbound contracts can be staged as deliveries."
                )
            if not record.contract_id.import_template_id:
                raise ValidationError(
                    "Inbound contracts must be linked to an import template."
                )
