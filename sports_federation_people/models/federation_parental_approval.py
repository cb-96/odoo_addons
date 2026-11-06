from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationPlayerParentalApproval(models.Model):
    _name = "federation.player.parental.approval"
    _description = "Player Parental Approval"
    _inherit = ["mail.thread"]
    _order = "approval_date desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    player_id = fields.Many2one(
        "federation.player",
        string="Player",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    guardian_name = fields.Char(
        string="Parent / Guardian", required=True, tracking=True
    )
    guardian_email = fields.Char(string="Guardian Email", tracking=True)
    approval_date = fields.Date(
        string="Approval Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    valid_until = fields.Date(string="Valid Until", tracking=True)
    approval_document = fields.Binary(
        string="Signed Approval",
        required=True,
        attachment=True,
    )
    approval_document_filename = fields.Char(string="Document Filename")
    submitted_by_id = fields.Many2one(
        "res.users", string="Submitted By", readonly=True, copy=False, ondelete="set null"
    )
    submitted_on = fields.Datetime(string="Submitted On", readonly=True, copy=False)
    review_note = fields.Text(
        string="Review Note",
        help="Federation feedback shown to the submitting club when replacement is required.",
        copy=False,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("verified", "Verified"),
            ("replacement_requested", "Replacement Required"),
            ("revoked", "Revoked"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    verified_on = fields.Datetime(readonly=True, copy=False)
    verified_by_id = fields.Many2one(
        "res.users",
        string="Verified By",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )
    revocation_reason = fields.Text(copy=False)
    notes = fields.Text()

    @api.depends("player_id", "guardian_name", "approval_date")
    def _compute_name(self):
        for record in self:
            parts = [
                record.player_id.display_name if record.player_id else False,
                record.guardian_name,
                str(record.approval_date) if record.approval_date else False,
            ]
            record.name = " – ".join(part for part in parts if part) or _(
                "New Parental Approval"
            )

    @api.constrains("approval_date", "valid_until")
    def _check_validity_dates(self):
        for record in self:
            if record.valid_until and record.valid_until < record.approval_date:
                raise ValidationError(
                    _("Parental approval cannot expire before its approval date.")
                )

    def write(self, vals):
        protected_fields = {
            "player_id",
            "guardian_name",
            "guardian_email",
            "approval_date",
            "valid_until",
            "approval_document",
            "approval_document_filename",
            "submitted_by_id",
            "submitted_on",
        }
        workflow_change = "state" in vals and any(
            record.state != vals["state"] for record in self
        )
        if workflow_change and not self.env.context.get(
            "allow_verified_parental_approval_write"
        ):
            raise ValidationError(
                _("Use the Verify or Revoke action to change approval status.")
            )
        if (
            protected_fields.intersection(vals)
            and not self.env.context.get("allow_verified_parental_approval_write")
            and self.filtered(lambda record: record.state != "draft")
        ):
            raise ValidationError(
                _(
                    "Verified or revoked parental approvals are retained as "
                    "evidence and cannot be edited."
                )
            )
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda record: record.state != "draft"):
            raise ValidationError(
                _(
                    "Verified or revoked parental approvals are retained as "
                    "evidence. Revoke a verified approval instead of deleting it."
                )
            )
        return super().unlink()

    def action_verify(self):
        for record in self:
            if record.state != "draft":
                raise ValidationError(
                    _("Only draft parental approvals can be verified.")
                )
            if not record.approval_document:
                raise ValidationError(
                    _("Attach the signed parental approval before verifying it.")
                )
        self.with_context(allow_verified_parental_approval_write=True).write(
            {
                "state": "verified",
                "verified_on": fields.Datetime.now(),
                "verified_by_id": self.env.user.id,
            }
        )
        return True

    def action_request_replacement(self):
        for record in self:
            if record.state != "draft":
                raise ValidationError(_("Only draft parental approvals can require replacement."))
            if not (record.review_note or "").strip():
                raise ValidationError(_("Record a review note before requesting replacement."))
        self.with_context(allow_verified_parental_approval_write=True).write(
            {"state": "replacement_requested"}
        )
        return True

    def action_revoke(self):
        for record in self:
            if record.state != "verified":
                raise ValidationError(
                    _("Only verified parental approvals can be revoked.")
                )
            if not record.revocation_reason:
                raise ValidationError(
                    _("Record a revocation reason before revoking the approval.")
                )
        self.with_context(allow_verified_parental_approval_write=True).write(
            {"state": "revoked"}
        )
        return True