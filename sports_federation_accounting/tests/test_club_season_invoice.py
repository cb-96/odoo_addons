from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_season_players")
class TestClubSeasonPlayerInvoice(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create({"name": "Grouped Annual Invoice Club"})
        cls.season = cls.env["federation.season"].create({
            "name": "Grouped Invoice Season", "date_start": "2098-01-01",
            "date_end": "2098-12-31", "state": "open",
        })
        cls.registration = cls.env["federation.club.season.registration"]._get_or_create(cls.club, cls.season)
        cls.registration.billing_partner_id = cls.env["res.partner"].create({"name": "Annual Club Customer"})
        cls.registration.invoice_product_id = cls.env["product.product"].create({"name": "Annual Registration", "type": "service"})
        cls.fee = cls.env.ref("sports_federation_finance_bridge.fee_type_player_season_registration")
        cls.fee.default_amount = 25
        cls.players = cls.env["federation.player"].create([
            {"first_name": name, "last_name": "Invoice", "club_id": cls.club.id,
             "gender": "male", "birth_date": "2000-01-01"}
            for name in ("First", "Second")
        ])

    def _events(self):
        return self.env["federation.finance.event"].search([
            ("source_model", "=", "federation.player.license"),
            ("source_res_id", "in", self.registration.license_ids.ids),
            ("fee_type_id", "=", self.fee.id),
        ])

    def test_grouped_invoice_and_retry(self):
        self.registration._add_players(self.players)
        self.registration.action_confirm()
        self._events().action_confirm()
        action = self.registration.action_create_player_invoice()
        invoice = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(invoice.state, "draft")
        self.assertEqual(len(invoice.invoice_line_ids), 2)
        self.assertEqual(self._events().mapped("account_move_id"), invoice)
        with self.assertRaises(ValidationError):
            self.registration.action_create_player_invoice()
        self.assertEqual(self._events().mapped("account_move_id"), invoice)

    def test_unconfirmed_charges_are_not_invoiced(self):
        self.registration._add_players(self.players)
        self.registration.action_confirm()
        with self.assertRaises(ValidationError):
            self.registration.action_create_player_invoice()
