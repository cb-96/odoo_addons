from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationPlayerSeasonRegistrationFinance(models.Model):
    _inherit = "federation.player.license"

    @api.model_create_multi
    def create(self, vals_list):
        licenses = super().create(vals_list)
        licenses.filtered(lambda item: item.state == "active")._ensure_player_season_fee()
        return licenses

    def write(self, vals):
        result = super().write(vals)
        if vals.get("state") == "active":
            self.filtered(lambda item: item.state == "active")._ensure_player_season_fee()
        return result

    def _ensure_player_season_fee(self):
        for license in self:
            company = license.club_registration_id.company_id
            Fee = self.env["federation.fee.type"].sudo().with_company(company)
            fee = Fee.search([
                ("code", "=", "player_season_registration"),
                ("company_id", "=", company.id),
            ], limit=1)
            if not fee:
                try:
                    with self.env.cr.savepoint():
                        fee = Fee.create({
                            "name": _("Season Player Registration Fee"),
                            "code": "player_season_registration", "category": "registration",
                            "default_amount": 0, "company_id": company.id,
                            "currency_id": company.currency_id.id,
                        })
                except IntegrityError:
                    fee = Fee.search([
                        ("code", "=", "player_season_registration"),
                        ("company_id", "=", company.id),
                    ], limit=1)
                    if not fee:
                        raise
            scheduled = self.env["federation.fee.schedule"].sudo().with_company(company).lookup_amount(
                fee, license.season_id, license.category, license.player_id.gender,
            )
            amount = fee.default_amount if scheduled is False else scheduled
            partner = license.club_registration_id.billing_partner_id
            if amount > 0 and not partner:
                raise ValidationError(_("Set the club billing contact before approving paid player registrations."))
            self.env["federation.finance.event"].sudo().with_company(company).ensure_from_source(
                license, fee, amount=amount, partner=partner,
                note=_("Annual player registration: %(player)s / %(season)s",
                       player=license.player_id.display_name, season=license.season_id.display_name),
            )


class FederationSeasonTeamFeePolicy(models.Model):
    _inherit = "federation.season"

    team_registration_fee_enabled = fields.Boolean(
        string="Also Charge Annual Team Enrolment", default=False,
        help="Player registration fees are independent of team entry. Enable only if a separate annual team fee is intended.",
    )


class FederationClubSeasonRegistrationFinance(models.Model):
    _inherit = "federation.club.season.registration"

    billing_partner_id = fields.Many2one(
        "res.partner", string="Club Billing Contact",
        help="Customer receiving the club's annual player registration invoice.",
    )

    def action_view_player_charges(self):
        self.ensure_one()
        self.check_access("read")
        return {
            "type": "ir.actions.act_window", "name": _("Season Player Charges"),
            "res_model": "federation.finance.event", "view_mode": "list,form",
            "domain": [("source_model", "=", "federation.player.license"),
                       ("source_res_id", "in", self.license_ids.ids),
                       ("fee_type_id.code", "=", "player_season_registration")],
        }

    def write(self, vals):
        if "company_id" in vals:
            events = self.env["federation.finance.event"].sudo().search_count([
                ("source_model", "=", "federation.player.license"),
                ("source_res_id", "in", self.mapped("license_ids").ids),
            ])
            if events:
                raise ValidationError(_("Company ownership cannot change after player charges exist."))
        return super().write(vals)
