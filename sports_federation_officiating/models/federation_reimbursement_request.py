import base64
import csv
import io
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class FederationReimbursementRequest(models.Model):
    _name = "federation.reimbursement.request"
    _description = "Referee Reimbursement Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "state, create_date desc"

    STATE_SELECTION = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
    ]

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        tracking=True,
    )
    referee_id = fields.Many2one(
        "federation.referee",
        string="Referee",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    match_id = fields.Many2one(
        "federation.match",
        string="Match",
        ondelete="set null",
        index=True,
    )
    amount = fields.Float(
        string="Amount",
        required=True,
        digits=(16, 2),
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    state = fields.Selection(
        STATE_SELECTION,
        string="Status",
        default="draft",
        required=True,
        tracking=True,
    )
    notes = fields.Text(string="Notes")
    payment_ref = fields.Char(
        string="Payment Reference",
        copy=False,
        tracking=True,
        help="Bank transfer reference set when the request is marked as paid.",
    )
    paid_on = fields.Date(string="Paid On", copy=False, readonly=True)

    @api.constrains("amount")
    def _check_amount(self):
        for req in self:
            if req.amount < 0:
                raise ValidationError(_("Reimbursement amount cannot be negative."))

    def action_submit(self):
        """Submit draft reimbursement requests for approval."""
        invalid = self.filtered(lambda r: r.state != "draft")
        if invalid:
            raise ValidationError(_("Only draft requests can be submitted."))
        self.write({"state": "submitted"})

    def action_approve(self):
        """Approve submitted reimbursement requests."""
        invalid = self.filtered(lambda r: r.state != "submitted")
        if invalid:
            raise ValidationError(_("Only submitted requests can be approved."))
        self.write({"state": "approved"})

    def action_mark_paid(self):
        """Mark approved requests as paid using the payment_ref field."""
        invalid = self.filtered(lambda r: r.state != "approved")
        if invalid:
            raise ValidationError(_("Only approved requests can be marked as paid."))
        self.write({"state": "paid", "paid_on": date.today()})

    def action_cancel(self):
        """Cancel requests that have not yet been paid."""
        invalid = self.filtered(lambda r: r.state == "paid")
        if invalid:
            raise ValidationError(_("Paid requests cannot be cancelled."))
        self.write({"state": "cancelled"})

    def action_reset_draft(self):
        """Reset cancelled requests back to draft."""
        invalid = self.filtered(lambda r: r.state != "cancelled")
        if invalid:
            raise ValidationError(_("Only cancelled requests can be reset to draft."))
        self.write({"state": "draft", "payment_ref": False, "paid_on": False})

    def action_export_bank_transfer_csv(self):
        """Generate a CSV file of approved requests for bank-transfer processing.

        The export covers the selected records that are in ``approved`` state.
        Returns a download action pointing to an ``ir.attachment``.
        """
        approved = self.filtered(lambda r: r.state == "approved")
        if not approved:
            raise UserError(
                _("No approved reimbursement requests to export for bank transfer.")
            )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["Reference", "Referee", "Match", "Amount", "Currency", "Notes"]
        )
        for req in approved:
            writer.writerow(
                [
                    req.name,
                    req.referee_id.name,
                    req.match_id.name if req.match_id else "",
                    f"{req.amount:.2f}",
                    req.currency_id.name,
                    req.notes or "",
                ]
            )

        csv_bytes = output.getvalue().encode("utf-8")
        attachment = self.env["ir.attachment"].create(
            {
                "name": "reimbursements_bank_transfer.csv",
                "type": "binary",
                "datas": base64.b64encode(csv_bytes).decode("utf-8"),
                "mimetype": "text/csv",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }
