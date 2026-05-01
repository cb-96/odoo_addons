from odoo import api, models


class FederationMatchRefereeFinanceHooks(models.Model):
    _inherit = "federation.match.referee"

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        assignments = super().create(vals_list)
        assignments._sync_reimbursement_finance_event()
        return assignments

    def write(self, vals):
        """Update records with module-specific side effects."""
        should_sync = any(
            key in vals for key in ("state", "referee_id", "match_id", "role")
        )
        res = super().write(vals)
        if should_sync:
            self._sync_reimbursement_finance_event()
        return res

    def _sync_reimbursement_finance_event(self):
        """Synchronize reimbursement finance event."""
        FinanceEvent = self.env["federation.finance.event"]
        role_labels = dict(self._fields["role"].selection)
        for assignment in self:
            fee_type = assignment._get_referee_reimbursement_fee_type(
                create_if_missing=assignment.state == "done"
            )
            existing_event = fee_type and FinanceEvent.search(
                [
                    ("fee_type_id", "=", fee_type.id),
                    ("source_model", "=", assignment._name),
                    ("source_res_id", "=", assignment.id),
                ],
                limit=1,
            )

            if assignment.state == "done" and fee_type:
                FinanceEvent.ensure_from_source(
                    assignment,
                    fee_type,
                    amount=fee_type.default_amount,
                    event_type="reimbursement",
                    note=(
                        "Auto: referee reimbursement for "
                        f"{role_labels.get(assignment.role, assignment.role)} on {assignment.match_id.name}"
                    ),
                    extra_vals={"referee_id": assignment.referee_id.id},
                    update_existing=True,
                )
            elif existing_event and existing_event.state == "draft":
                existing_event.action_cancel()

    def _get_referee_reimbursement_fee_type(self, create_if_missing=True):
        """Return referee reimbursement fee type."""
        self.ensure_one()
        fee_type = self.env["federation.fee.type"].search(
            [("code", "=", "referee_reimbursement")],
            limit=1,
        )
        if fee_type or not create_if_missing:
            return fee_type

        return self.env["federation.fee.type"].create(
            {
                "name": "Referee Reimbursement",
                "code": "referee_reimbursement",
                "category": "reimbursement",
                "default_amount": 0.0,
                "currency_id": self.env.company.currency_id.id,
            }
        )
