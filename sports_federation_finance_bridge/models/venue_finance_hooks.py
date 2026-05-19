from odoo import api, models
from odoo.exceptions import ValidationError


class FederationMatchVenueFinanceHooks(models.Model):
    _inherit = "federation.match"

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        matches = super().create(vals_list)
        matches._sync_venue_finance_event()
        return matches

    def write(self, vals):
        """Update records with module-specific side effects."""
        should_sync = any(key in vals for key in ("state", "venue_id"))
        res = super().write(vals)
        if should_sync:
            self._sync_venue_finance_event()
        return res

    def _sync_venue_finance_event(self):
        """Synchronize venue finance event."""
        FinanceEvent = self.env["federation.finance.event"]
        for match in self:
            fee_type = match._get_venue_fee_type(
                create_if_missing=bool(match.venue_id and match.state == "scheduled")
            )
            existing_event = fee_type and FinanceEvent.search(
                [
                    ("fee_type_id", "=", fee_type.id),
                    ("source_model", "=", match._name),
                    ("source_res_id", "=", match.id),
                ],
                limit=1,
            )

            if match.state == "scheduled" and match.venue_id and fee_type:
                FinanceEvent.ensure_from_source(
                    match,
                    fee_type,
                    amount=fee_type.default_amount,
                    event_type="charge",
                    note=f"Auto: venue booking for {match.name} at {match.venue_id.name}",
                    update_existing=True,
                )
            elif existing_event and existing_event.state == "draft":
                existing_event.action_cancel()

    def _get_venue_fee_type(
        self, create_if_missing=True, fee_type_code="venue_booking"
    ):
        """Return venue fee type."""
        self.ensure_one()
        fee_type = self.env["federation.fee.type"].search(
            [("code", "=", fee_type_code)],
            limit=1,
        )
        if fee_type or not create_if_missing:
            return fee_type

        return self.env["federation.fee.type"].create(
            {
                "name": "Venue Booking",
                "code": fee_type_code,
                "category": "other",
                "default_amount": 0.0,
                "currency_id": self.env.company.currency_id.id,
            }
        )

    def action_create_venue_finance_event(
        self, fee_type_code="venue_booking", amount=None, partner=None, note=None
    ):
        """Execute the create venue finance event action."""
        events = self.env["federation.finance.event"]

        for match in self:
            if not match.venue_id:
                raise ValidationError(
                    "Match has no venue set; cannot create finance event."
                )

            fee_type = match._get_venue_fee_type(
                create_if_missing=True, fee_type_code=fee_type_code
            )
            event = self.env["federation.finance.event"].ensure_from_source(
                match,
                fee_type,
                amount=amount if amount is not None else fee_type.default_amount,
                event_type="charge",
                partner=partner,
                note=note or f"Venue booking for {match.name} at {match.venue_id.name}",
                update_existing=True,
            )
            events |= event

        return events
