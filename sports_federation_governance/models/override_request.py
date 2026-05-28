from odoo import api, fields, models
from odoo.addons.sports_federation_governance.workflow_states import (
    OVERRIDE_REQUEST_CLOSABLE_STATES,
    OVERRIDE_REQUEST_STATE_APPROVED,
    OVERRIDE_REQUEST_STATE_CLOSED,
    OVERRIDE_REQUEST_STATE_DRAFT,
    OVERRIDE_REQUEST_STATE_IMPLEMENTED,
    OVERRIDE_REQUEST_STATE_REJECTED,
    OVERRIDE_REQUEST_STATE_SELECTION,
    OVERRIDE_REQUEST_STATE_SUBMITTED,
    is_override_request_approved,
    is_override_request_submitted,
)
from odoo.exceptions import ValidationError


class FederationOverrideRequest(models.Model):
    _name = "federation.override.request"
    _description = "Federation Override Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "requested_on desc, id"

    REQUEST_TYPE_SELECTION = [
        ("manual_seeding", "Manual Seeding"),
        ("eligibility_waiver", "Eligibility Waiver"),
        ("late_registration", "Late Registration"),
        ("result_correction", "Result Correction"),
        ("standing_adjustment", "Standing Adjustment"),
        ("admin_forfeit", "Administrative Forfeit"),
        ("other", "Other"),
    ]

    STATE_SELECTION = OVERRIDE_REQUEST_STATE_SELECTION

    name = fields.Char(string="Title", required=True, tracking=True)
    request_type = fields.Selection(
        selection=REQUEST_TYPE_SELECTION,
        string="Request Type",
        required=True,
    )
    target_model = fields.Char(string="Target Model", required=True)
    target_res_id = fields.Integer(string="Target Record ID", required=True)
    requested_by_id = fields.Many2one(
        "res.users",
        string="Requested By",
        default=lambda self: self.env.user,
        required=True,
    )
    requested_on = fields.Datetime(
        string="Requested On",
        default=fields.Datetime.now,
        required=True,
    )
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="State",
        default=OVERRIDE_REQUEST_STATE_DRAFT,
        required=True,
        tracking=True,
    )
    reason = fields.Text(string="Reason", required=True)
    implementation_note = fields.Text(string="Implementation Note")
    decision_ids = fields.One2many(
        "federation.override.decision",
        "request_id",
        string="Decisions",
    )
    audit_note_ids = fields.One2many(
        "federation.audit.note",
        "request_id",
        string="Audit Notes",
    )
    outcome_ids = fields.One2many(
        "federation.override.outcome",
        "request_id",
        string="Outcome Log",
    )

    @api.constrains("target_model")
    def _check_target_model(self):
        """Validate target model."""
        for record in self:
            if not record.target_model:
                raise ValidationError("Target model must not be empty.")

    @api.constrains("target_res_id")
    def _check_target_res_id(self):
        """Validate target res ID."""
        for record in self:
            if record.target_res_id <= 0:
                raise ValidationError("Target record ID must be > 0.")

    @api.constrains("reason")
    def _check_reason(self):
        """Validate reason."""
        for record in self:
            if not record.reason or not record.reason.strip():
                raise ValidationError("Reason is required.")

    def action_submit(self):
        """Submit the request for approval."""
        for record in self:
            if record.state != OVERRIDE_REQUEST_STATE_DRAFT:
                raise ValidationError("Only draft requests can be submitted.")
            record.state = OVERRIDE_REQUEST_STATE_SUBMITTED

    def action_withdraw(self):
        """Withdraw a submitted request back to draft."""
        for record in self:
            if not is_override_request_submitted(record.state):
                raise ValidationError("Only submitted requests can be withdrawn.")
            record.state = OVERRIDE_REQUEST_STATE_DRAFT

    def action_approve(self):
        """Approve the request and create decision record."""
        for record in self:
            if not is_override_request_submitted(record.state):
                raise ValidationError("Only submitted requests can be approved.")
            record.state = OVERRIDE_REQUEST_STATE_APPROVED
            # Create decision record
            self.env["federation.override.decision"].create(
                {
                    "request_id": record.id,
                    "decision": OVERRIDE_REQUEST_STATE_APPROVED,
                }
            )

    def action_reject(self):
        """Reject the request and create decision record."""
        for record in self:
            if not is_override_request_submitted(record.state):
                raise ValidationError("Only submitted requests can be rejected.")
            record.state = OVERRIDE_REQUEST_STATE_REJECTED
            # Create decision record
            self.env["federation.override.decision"].create(
                {
                    "request_id": record.id,
                    "decision": OVERRIDE_REQUEST_STATE_REJECTED,
                }
            )

    def action_mark_implemented(self):
        """Mark the request as implemented."""
        for record in self:
            if not is_override_request_approved(record.state):
                raise ValidationError(
                    "Only approved requests can be marked as implemented."
                )
            record.state = OVERRIDE_REQUEST_STATE_IMPLEMENTED
            self.env["federation.override.outcome"].create(
                {
                    "request_id": record.id,
                    "outcome": OVERRIDE_REQUEST_STATE_IMPLEMENTED,
                    "note": record.implementation_note
                    or "Override marked as implemented.",
                }
            )

    def action_close(self):
        """Close the request."""
        for record in self:
            if record.state not in OVERRIDE_REQUEST_CLOSABLE_STATES:
                raise ValidationError(
                    "Only implemented or rejected requests can be closed."
                )
            record.state = OVERRIDE_REQUEST_STATE_CLOSED
