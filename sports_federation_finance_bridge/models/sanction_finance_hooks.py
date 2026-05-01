from odoo import api, models


class FederationSanctionFinanceHooks(models.Model):
    _inherit = "federation.sanction"

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        sanctions = super().create(vals_list)
        sanctions._sync_fine_finance_event()
        return sanctions

    def write(self, vals):
        """Update records with module-specific side effects."""
        should_sync = any(
            key in vals
            for key in (
                "sanction_type",
                "amount",
                "player_id",
                "club_id",
                "referee_id",
                "case_id",
            )
        )
        res = super().write(vals)
        if should_sync:
            self._sync_fine_finance_event()
        return res

    def _sync_fine_finance_event(self):
        """Synchronize fine finance event."""
        FinanceEvent = self.env["federation.finance.event"]
        for sanction in self:
            fee_type = sanction._get_discipline_fine_fee_type(
                create_if_missing=sanction.sanction_type == "fine"
            )
            existing_event = fee_type and FinanceEvent.search(
                [
                    ("fee_type_id", "=", fee_type.id),
                    ("source_model", "=", sanction._name),
                    ("source_res_id", "=", sanction.id),
                ],
                limit=1,
            )

            if sanction.sanction_type == "fine" and fee_type:
                subject_vals = sanction._get_finance_subject_vals()
                amount = sanction.amount if sanction.amount else fee_type.default_amount
                FinanceEvent.ensure_from_source(
                    sanction,
                    fee_type,
                    amount=amount,
                    event_type="charge",
                    note=(
                        "Auto: disciplinary fine for "
                        f"{sanction.case_id.reference or sanction.case_id.name}"
                    ),
                    extra_vals=subject_vals,
                    update_existing=True,
                )
            elif existing_event and existing_event.state == "draft":
                existing_event.action_cancel()

    def _get_finance_subject_vals(self):
        """Return finance subject vals."""
        self.ensure_one()
        player = self.player_id or self.case_id.subject_player_id
        club = self.club_id or self.case_id.subject_club_id
        referee = self.referee_id or self.case_id.subject_referee_id
        return {
            "player_id": player.id if player else False,
            "club_id": club.id if club else False,
            "referee_id": referee.id if referee else False,
        }

    def _get_discipline_fine_fee_type(self, create_if_missing=True):
        """Return discipline fine fee type."""
        self.ensure_one()
        fee_type = self.env["federation.fee.type"].search(
            [("code", "=", "discipline_fine")],
            limit=1,
        )
        if fee_type or not create_if_missing:
            return fee_type

        return self.env["federation.fee.type"].create(
            {
                "name": "Disciplinary Fine",
                "code": "discipline_fine",
                "category": "fine",
                "default_amount": 0.0,
                "currency_id": self.env.company.currency_id.id,
            }
        )
