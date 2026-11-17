from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FederationFinanceEventPayment(models.Model):
    _inherit = "federation.finance.event"

    settlement_ids = fields.One2many(
        "federation.finance.settlement", "event_id", readonly=True
    )
    paid_amount = fields.Monetary(
        compute="_compute_payment_position", currency_field="currency_id"
    )
    refunded_amount = fields.Monetary(
        compute="_compute_payment_position", currency_field="currency_id"
    )
    balance_amount = fields.Monetary(
        compute="_compute_payment_position", currency_field="currency_id"
    )
    payment_exception_state = fields.Selection(
        [
            ("none", "No exception"),
            ("unpaid", "Unpaid"),
            ("partial", "Partially paid"),
            ("failed", "Payment failed"),
            ("refunded", "Refunded"),
            ("reconciled", "Reconciled"),
        ],
        compute="_compute_payment_position",
    )

    @api.depends(
        "amount",
        "state",
        "handoff_state",
        "settlement_ids.state",
        "settlement_ids.amount",
    )
    def _compute_payment_position(self):
        for event in self:
            succeeded = event.settlement_ids.filtered(
                lambda row: row.state == "succeeded"
            )
            refunded = event.settlement_ids.filtered(
                lambda row: row.state == "refunded"
            )
            paid = sum(succeeded.mapped("amount"))
            returned = sum(refunded.mapped("amount"))
            event.paid_amount = paid
            event.refunded_amount = returned
            event.balance_amount = max(event.amount - paid + returned, 0)
            if (
                event.handoff_state in ("reconciled", "closed")
                and not event.balance_amount
            ):
                state = "reconciled"
            elif refunded:
                state = "refunded"
            elif event.settlement_ids.filtered(lambda row: row.state == "failed"):
                state = "failed"
            elif paid and event.balance_amount:
                state = "partial"
            elif event.event_type == "charge" and event.state == "confirmed":
                state = "unpaid"
            else:
                state = "none"
            event.payment_exception_state = state

    def action_settle(self):
        tracked = self.filtered("settlement_ids")
        if tracked.filtered(
            lambda event: not event.currency_id.is_zero(event.balance_amount)
        ):
            raise ValidationError(
                _(
                    "Record successful payments for the full obligation before "
                    "settling it."
                )
            )
        return super().action_settle()


class FederationFinanceSettlement(models.Model):
    _name = "federation.finance.settlement"
    _description = "Finance Payment or Refund Evidence"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "occurred_on desc,id desc"

    event_id = fields.Many2one(
        "federation.finance.event", required=True, ondelete="restrict", index=True
    )
    company_id = fields.Many2one(related="event_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="event_id.currency_id", store=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("succeeded", "Succeeded"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
            ("refunded", "Refunded"),
        ],
        default="pending",
        required=True,
        tracking=True,
        index=True,
    )
    provider = fields.Char(help="Optional payment-provider name.")
    provider_reference = fields.Char(index=True)
    occurred_on = fields.Datetime(default=fields.Datetime.now, required=True)
    failure_reason = fields.Text()
    refund_of_id = fields.Many2one(
        "federation.finance.settlement", ondelete="restrict", index=True
    )
    reconciled = fields.Boolean(readonly=True)
    reconciliation_reference = fields.Char(readonly=True)
    reconciled_on = fields.Datetime(readonly=True)
    reconciled_by_id = fields.Many2one("res.users", readonly=True)

    _provider_ref_unique = models.Constraint(
        "unique(company_id,provider,provider_reference)",
        "Provider payment references must be unique per company.",
    )

    @api.constrains("amount", "event_id", "refund_of_id")
    def _check_position(self):
        for row in self:
            if row.amount <= 0:
                raise ValidationError(_("Payment and refund amounts must be positive."))
            if row.refund_of_id and row.refund_of_id.event_id != row.event_id:
                raise ValidationError(
                    _("A refund must reference a payment on this obligation.")
                )
            if row.refund_of_id and row.amount > row.refund_of_id.amount:
                raise ValidationError(_("A refund cannot exceed its original payment."))

    def _assert_finance_manager(self):
        if not self.env.user.has_group(
            "sports_federation_base.group_federation_manager"
        ):
            raise AccessError(
                _("Only federation finance managers can record settlement evidence.")
            )

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_finance_manager()
        if any(values.get("state", "pending") != "pending" for values in vals_list):
            raise ValidationError(
                _("Create settlement evidence as pending, then use a command.")
            )
        return super().create(vals_list)

    def action_succeed(self):
        self._assert_finance_manager()
        for row in self:
            if row.state != "pending":
                raise ValidationError(_("Only pending payment evidence can succeed."))
            row.state = "succeeded"
        return True

    def action_fail(self):
        self._assert_finance_manager()
        for row in self:
            if row.state != "pending" or not (row.failure_reason or "").strip():
                raise ValidationError(
                    _("Record a failure reason for a pending payment.")
                )
            row.state = "failed"
        return True

    def action_cancel(self):
        self._assert_finance_manager()
        for row in self:
            if row.state not in ("pending", "failed"):
                raise ValidationError(
                    _("Only pending or failed evidence can be cancelled.")
                )
            row.state = "cancelled"
        return True

    def action_refund(self):
        self._assert_finance_manager()
        created = self.browse()
        for row in self:
            if row.state != "succeeded":
                raise ValidationError(_("Only a successful payment can be refunded."))
            refund = self.create(
                {
                    "event_id": row.event_id.id,
                    "amount": row.amount,
                    "provider": row.provider,
                    "provider_reference": (
                        "%s-refund" % row.provider_reference
                        if row.provider_reference
                        else False
                    ),
                    "refund_of_id": row.id,
                }
            )
            refund.state = "refunded"
            created |= refund
        return created.get_formview_action() if len(created) == 1 else True

    def action_reconcile(self, reference=False):
        self._assert_finance_manager()
        if not (reference or "").strip():
            raise ValidationError(_("A reconciliation reference is required."))
        for row in self:
            if row.state not in ("succeeded", "refunded"):
                raise ValidationError(
                    _("Only successful or refunded evidence can be reconciled.")
                )
            row.write(
                {
                    "reconciled": True,
                    "reconciliation_reference": reference.strip(),
                    "reconciled_on": fields.Datetime.now(),
                    "reconciled_by_id": self.env.user.id,
                }
            )
        return True
