from odoo import api, models


class FederationSeasonRegistrationFinanceHooks(models.Model):
    _inherit = "federation.season.registration"

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        registrations = super().create(vals_list)
        registrations.filtered(
            lambda rec: rec.state == "confirmed"
        )._ensure_registration_finance_event()
        return registrations

    def write(self, vals):
        """Update records with module-specific side effects."""
        should_create_events = vals.get("state") == "confirmed"
        res = super().write(vals)
        if should_create_events:
            self.filtered(
                lambda rec: rec.state == "confirmed"
            )._ensure_registration_finance_event()
        return res

    def _ensure_registration_finance_event(self):
        """Handle ensure registration finance event."""
        finance_event_model = self.env["federation.finance.event"].sudo()
        fee_schedule_model = self.env["federation.fee.schedule"].sudo()
        for registration in self:
            registration_sudo = registration.sudo()
            fee_type = registration_sudo._get_registration_fee_type()
            partner = False
            if "partner_id" in registration_sudo._fields:
                partner = registration_sudo.partner_id

            # Resolve scheduled amount based on team category/gender in this season
            amount = None
            team = registration_sudo.team_id
            if team and registration_sudo.season_id:
                scheduled = fee_schedule_model.lookup_amount(
                    fee_type,
                    registration_sudo.season_id,
                    team.category,
                    team.gender,
                )
                if scheduled is not False:
                    amount = scheduled

            finance_event_model.ensure_from_source(
                registration_sudo,
                fee_type,
                amount=amount,
                event_type="charge",
                partner=partner,
                note=(
                    "Auto: season registration confirmed for "
                    f"{registration_sudo.team_id.display_name} in {registration_sudo.season_id.display_name}"
                ),
            )

    def _get_registration_fee_type(self):
        """Return registration fee type."""
        self.ensure_one()
        fee_type_model = self.env["federation.fee.type"].sudo()
        fee_type = fee_type_model.search(
            [("code", "=", "season_registration")],
            limit=1,
        )
        if fee_type:
            return fee_type

        return fee_type_model.create(
            {
                "name": "Season Registration Fee",
                "code": "season_registration",
                "category": "registration",
                "default_amount": 0.0,
                "currency_id": self.env.company.currency_id.id,
            }
        )
