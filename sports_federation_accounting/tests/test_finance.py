from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_release_confidence")
class TestNativeFinanceInvoice(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Native Finance Invoice Customer"}
        )
        cls.fee_type = cls.env["federation.fee.type"].create(
            {
                "name": "Native Finance Invoice Fee",
                "code": "NATIVE_INVOICE_TEST",
                "category": "registration",
                "default_amount": 125.0,
                "currency_id": cls.env.company.currency_id.id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Native Finance Invoice Service", "type": "service"}
        )

    def _event(self, **values):
        vals = {
            "name": "Native invoice retry test",
            "fee_type_id": self.fee_type.id,
            "event_type": "charge",
            "amount": 125.0,
            "currency_id": self.env.company.currency_id.id,
            "source_model": "res.partner",
            "source_res_id": self.partner.id,
            "partner_id": self.partner.id,
            "state": "confirmed",
            "invoice_product_id": self.product.id,
        }
        vals.update(values)
        return self.env["federation.finance.event"].create(vals)

    def test_native_invoice_creation_is_retry_safe(self):
        event = self._event()

        first_action = event.action_create_invoice()
        invoice = event.account_move_id
        self.assertTrue(invoice)
        self.assertEqual(first_action["res_model"], "account.move")
        self.assertEqual(first_action["res_id"], invoice.id)
        self.assertEqual(invoice.move_type, "out_invoice")
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertEqual(len(invoice.invoice_line_ids), 1)
        self.assertEqual(invoice.invoice_line_ids.price_unit, 125.0)

        replay_action = event.action_create_invoice()
        self.assertEqual(replay_action["res_id"], invoice.id)
        self.assertEqual(event.account_move_id, invoice)
        self.assertEqual(
            self.env["account.move"].search_count(
                [("invoice_origin", "=", event.name)]
            ),
            1,
        )

    def test_native_invoice_requires_a_payer(self):
        event = self._event(partner_id=False)
        with self.assertRaises(ValidationError):
            event.action_create_invoice()
        self.assertFalse(event.account_move_id)
