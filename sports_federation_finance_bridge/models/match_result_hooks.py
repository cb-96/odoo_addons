"""Finance bridge hooks for match result approval.

When a match result is approved (via ``sports_federation_result_control``),
this model automatically creates a ``federation.finance.event`` if a
``result_fee_type_id`` is configured on the match.

This enables clubs and the federation to track per-match financial obligations
(e.g., referee reimbursements) without manual data entry.
"""

from odoo import fields, models


class FederationMatchFinanceHooks(models.Model):
    """Extends ``federation.match`` to auto-create finance events on result approval."""

    _inherit = "federation.match"

    result_fee_type_id = fields.Many2one(
        "federation.fee.type",
        string="Result Finance Fee Type",
        ondelete="set null",
        help=(
            "When set, a finance event is automatically created for this fee "
            "type when the match result is approved.  Leave empty to skip "
            "automatic event creation."
        ),
    )
    result_finance_event_ids = fields.One2many(
        "federation.finance.event",
        compute="_compute_result_finance_events",
        string="Result Finance Events",
    )

    def _compute_result_finance_events(self):
        """Compute finance events whose source is this match."""
        FinanceEvent = self.env["federation.finance.event"]
        for rec in self:
            domain = [
                ("source_model", "=", "federation.match"),
                ("source_res_id", "=", rec.id),
            ]
            if rec.result_fee_type_id:
                domain.append(("fee_type_id", "=", rec.result_fee_type_id.id))
            else:
                domain.append(("id", "=", 0))
            events = FinanceEvent.search(domain)
            rec.result_finance_event_ids = events

    def action_approve_result(self):
        """Override: approve result and optionally create an automatic finance event.

        Calls the result_control approval logic first, then creates a
        ``federation.finance.event`` for every match that has
        ``result_fee_type_id`` set.
        """
        res = super().action_approve_result()
        for rec in self:
            if rec.result_fee_type_id:
                self.env["federation.finance.event"].ensure_from_source(
                    rec,
                    rec.result_fee_type_id,
                    event_type="charge",
                    note=f"Auto: result approved for {rec.name}",
                )
        return res
