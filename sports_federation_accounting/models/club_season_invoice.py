from odoo import _, fields, models
from odoo.exceptions import AccessError, ValidationError

from .finance import Finance


class FederationClubSeasonInvoice(models.Model):
    _inherit = "federation.club.season.registration"

    invoice_product_id = fields.Many2one(
        "product.product", string="Player Registration Product"
    )

    def action_create_player_invoice(self):
        self.ensure_one()
        self.check_access("write")
        if not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(_("Invoice administration permission is required."))
        self.env.cr.execute(
            "SELECT id FROM federation_club_season_registration WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset()
        if not self.billing_partner_id or not self.invoice_product_id:
            raise ValidationError(
                _("Set the club billing contact and registration product first.")
            )
        company = self.company_id
        if company not in self.env.companies:
            raise AccessError(
                _("The registration company is not in your allowed companies.")
            )
        if (
            self.billing_partner_id.company_id
            and self.billing_partner_id.company_id != company
        ):
            raise ValidationError(_("The billing contact belongs to another company."))
        if (
            self.invoice_product_id.company_id
            and self.invoice_product_id.company_id != company
        ):
            raise ValidationError(
                _("The registration product belongs to another company.")
            )
        Event = self.env["federation.finance.event"].with_company(company)
        events = Event.search(
            [
                ("company_id", "=", company.id),
                ("source_model", "=", "federation.player.license"),
                ("source_res_id", "in", self.license_ids.ids),
                ("fee_type_id.code", "=", "player_season_registration"),
                ("event_type", "=", "charge"),
                ("state", "=", "confirmed"),
                ("amount", ">", 0),
                ("account_move_id", "=", False),
            ],
            order="id",
        )
        if not events:
            raise ValidationError(
                _("There are no confirmed, positive, uninvoiced player charges.")
            )
        events._finance_actor()
        events._finance_lock()
        events.invalidate_recordset()
        # Another invoice command may have linked an event while we waited.
        events = events.filtered(
            lambda event: not event.account_move_id and event.state == "confirmed"
        )
        if not events:
            raise ValidationError(_("These player charges have already been invoiced."))
        if any(event.currency_id != company.currency_id for event in events):
            raise ValidationError(
                _("Player charges must use the registration company's currency.")
            )
        if any(event.partner_id != self.billing_partner_id for event in events):
            raise ValidationError(
                _("Player charges have a different billing contact; review them first.")
            )
        events.write(
            {
                "invoice_product_id": self.invoice_product_id.id,
            }
        )
        move = (
            self.env["account.move"]
            .with_company(company)
            .create(
                {
                    "move_type": "out_invoice",
                    "company_id": company.id,
                    "partner_id": self.billing_partner_id.id,
                    "currency_id": company.currency_id.id,
                    "invoice_origin": self.display_name,
                    "invoice_line_ids": [
                        fields.Command.create(
                            {
                                "product_id": self.invoice_product_id.id,
                                "name": event.name,
                                "quantity": 1,
                                "price_unit": event.amount,
                            }
                        )
                        for event in events
                    ],
                }
            )
        )
        # Same command-owned linkage as the existing single-event invoice action.
        super(Finance, events).write(
            {"account_move_id": move.id, "invoice_ref": str(move.id)}
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
        }
