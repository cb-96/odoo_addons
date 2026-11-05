from odoo import api, fields, models

from .. import renewal_policy


class MembershipRenewalProgress(models.Model):
    """Shows where a renewal stands and what it is waiting for. Read-only."""

    _inherit = "federation.person.membership"

    renewal_step = fields.Selection(
        renewal_policy.STEPS, compute="_compute_renewal_progress", string="Renewal step"
    )
    renewal_blockers = fields.Text(compute="_compute_renewal_progress", string="Still to do")
    renewal_payment_note = fields.Char(compute="_compute_renewal_progress", string="Payment")

    @api.depends(
        "previous_id", "state", "review_note", "person_id.family_canonical_id", "finance_event_id.state"
    )
    def _compute_renewal_progress(self):
        persisted = self.filtered("id")
        today = fields.Date.today()
        documents = {}
        if persisted:
            requests = (
                self.env["federation.person.request"]
                .sudo()
                .search(
                    [
                        ("membership_id", "in", persisted.ids),
                        ("required_for_activation", "=", True),
                        ("state", "!=", "cancelled"),
                    ]
                )
            )
            for request in requests:
                documents.setdefault(request.membership_id.id, []).append(request)
        for membership in self:
            row = membership.sudo()
            unverified = sum(
                1
                for request in documents.get(membership.id, [])
                if not request._current_verified() or (request.valid_until and request.valid_until < today)
            )
            step, blockers = renewal_policy.progress(
                is_renewal=bool(row.previous_id),
                state=row.state,
                has_review_note=bool((row.review_note or "").strip()),
                unverified_documents=unverified,
                identity_current=not row.person_id.family_canonical_id,
            )
            membership.renewal_step = step
            membership.renewal_blockers = "\n".join(blockers) or False
            membership.renewal_payment_note = (
                renewal_policy.payment_note(row.finance_event_id.state) if row.previous_id else False
            )
