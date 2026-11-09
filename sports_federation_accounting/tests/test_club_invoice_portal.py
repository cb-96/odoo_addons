from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_club_invoices")
class TestClubInvoicePortal(TransactionCase):
    """Club representatives see their club's posted invoices and what is unpaid."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {"name": "Invoice Club", "code": "INVC"}
        )
        cls.other_club = cls.env["federation.club"].create(
            {"name": "Invoice Other Club", "code": "INVO"}
        )
        group = cls.env.ref("sports_federation_portal.group_federation_portal_club")
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Invoice Representative",
                    "login": "invoice.rep@example.com",
                    "group_ids": [(6, 0, [group.id])],
                }
            )
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club.id,
                "partner_id": cls.user.partner_id.id,
                "user_id": cls.user.id,
                "role_type_id": cls.env.ref(
                    "sports_federation_portal.role_type_competition_contact"
                ).id,
            }
        )
        cls.payer = cls.env["res.partner"].create({"name": "Invoice Club Treasurer"})
        cls.fee_type = cls.env["federation.fee.type"].create(
            {
                "name": "Club Invoice Fee",
                "code": "CLUB_INVOICE_TEST",
                "category": "registration",
                "default_amount": 50.0,
                "currency_id": cls.env.company.currency_id.id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Club Invoice Service", "type": "service"}
        )

    def _invoiced_charge(self, club, post=True):
        event = self.env["federation.finance.event"].create(
            {
                "name": "Season registration %s" % club.code,
                "fee_type_id": self.fee_type.id,
                "event_type": "charge",
                "amount": 50.0,
                "currency_id": self.env.company.currency_id.id,
                "source_model": "res.partner",
                "source_res_id": self.payer.id,
                "partner_id": self.payer.id,
                "charge_owner": "club",
                "club_id": club.id,
                "state": "confirmed",
                "invoice_product_id": self.product.id,
            }
        )
        event.action_create_invoice()
        if post:
            event.account_move_id.action_post()
        return event

    def test_only_posted_invoices_of_own_club_are_listed(self):
        own = self._invoiced_charge(self.club)
        self._invoiced_charge(self.club, post=False)
        self._invoiced_charge(self.other_club)
        Finance = self.env["federation.finance.event"]
        self.assertEqual(Finance._portal_club_invoices(user=self.user), own)
        rows = Finance._portal_club_invoice_rows(user=self.user)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["unpaid"])
        self.assertIn("access_token=", rows[0]["url"])
        self.assertEqual(Finance._portal_unpaid_invoice_count(user=self.user), 1)

    def test_users_without_club_scope_see_nothing(self):
        self._invoiced_charge(self.club)
        outsider = self.env["res.users"].create(
            {"name": "No Club", "login": "no.club.invoice@example.com"}
        )
        Finance = self.env["federation.finance.event"]
        self.assertFalse(Finance._portal_club_invoices(user=outsider))
        self.assertEqual(Finance._portal_unpaid_invoice_count(user=outsider), 0)
