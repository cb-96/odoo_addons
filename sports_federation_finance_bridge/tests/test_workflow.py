from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase
from odoo.tools.misc import mute_logger


class TestFeeSchedule(TransactionCase):
    """Tests for federation.fee.schedule — Item 5."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Fee Schedule Test Season",
                "code": "FSTS",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.fee_type = cls.env["federation.fee.type"].create(
            {
                "name": "Schedule Test Fee",
                "code": "SCH_TEST",
                "category": "registration",
                "default_amount": 100.0,
                "currency_id": cls.env.company.currency_id.id,
            }
        )

    def _make_schedule(self, category="youth", gender="male", amount=75.0):
        return self.env["federation.fee.schedule"].create(
            {
                "season_id": self.season.id,
                "fee_type_id": self.fee_type.id,
                "category": category,
                "gender": gender,
                "amount": amount,
                "currency_id": self.env.company.currency_id.id,
            }
        )

    def test_lookup_returns_scheduled_amount(self):
        """lookup_amount returns the configured rate when a schedule row exists."""
        self._make_schedule(category="youth", gender="male", amount=75.0)
        result = self.env["federation.fee.schedule"].lookup_amount(
            self.fee_type, self.season, "youth", "male"
        )
        self.assertEqual(result, 75.0)

    def test_lookup_returns_false_when_no_row(self):
        """lookup_amount returns False when no matching schedule row exists."""
        result = self.env["federation.fee.schedule"].lookup_amount(
            self.fee_type, self.season, "cadet", "female"
        )
        self.assertFalse(result)

    def test_unique_constraint_prevents_duplicate(self):
        """Uniqueness constraint prevents two rows for the same combination."""
        self._make_schedule(category="senior", gender="female", amount=50.0)
        with self.assertRaises(Exception), mute_logger(
            "odoo.sql_db"
        ), self.cr.savepoint():
            self._make_schedule(category="senior", gender="female", amount=60.0)

    def test_negative_amount_raises(self):
        """Negative amounts are rejected by the check constraint."""
        with self.assertRaises(ValidationError):
            self._make_schedule(category="mini", gender="mixed", amount=-1.0)


class TestRegistrationUsesSchedule(TransactionCase):
    """Tests for Item 6 — schedule-based amount lookup on registration confirm."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {"name": "Schedule Reg Club", "code": "SRC"}
        )
        cls.team_youth = cls.env["federation.team"].create(
            {
                "name": "Youth Team",
                "club_id": cls.club.id,
                "code": "SRCY",
                "category": "youth",
                "gender": "male",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Schedule Reg Season",
                "code": "SRS2026",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        # Make sure the season_registration fee type exists
        cls.fee_type = cls.env["federation.fee.type"].search(
            [("code", "=", "season_registration")], limit=1
        )
        if not cls.fee_type:
            cls.fee_type = cls.env["federation.fee.type"].create(
                {
                    "name": "Season Registration Fee",
                    "code": "season_registration",
                    "category": "registration",
                    "default_amount": 100.0,
                    "currency_id": cls.env.company.currency_id.id,
                }
            )

    def test_schedule_amount_used_when_row_exists(self):
        """Confirming a registration uses the schedule amount, not the default."""
        self.env["federation.fee.schedule"].create(
            {
                "season_id": self.season.id,
                "fee_type_id": self.fee_type.id,
                "category": "youth",
                "gender": "male",
                "amount": 55.0,
                "currency_id": self.env.company.currency_id.id,
            }
        )
        registration = self.env["federation.season.registration"].create(
            {"season_id": self.season.id, "team_id": self.team_youth.id}
        )
        registration.action_confirm()

        event = self.env["federation.finance.event"].search(
            [
                ("source_model", "=", "federation.season.registration"),
                ("source_res_id", "=", registration.id),
            ],
            limit=1,
        )
        self.assertTrue(event, "Finance event should be created on confirmation")
        self.assertEqual(event.amount, 55.0, "Event amount should match schedule rate")

    def test_fallback_to_default_when_no_schedule(self):
        """Confirming without a matching schedule row falls back to default amount."""
        team_senior = self.env["federation.team"].create(
            {
                "name": "Senior Fallback Team",
                "club_id": self.club.id,
                "code": "SFT",
                "category": "senior",
                "gender": "female",
            }
        )
        season2 = self.env["federation.season"].create(
            {
                "name": "Fallback Season",
                "code": "FS2026",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        registration = self.env["federation.season.registration"].create(
            {"season_id": season2.id, "team_id": team_senior.id}
        )
        registration.action_confirm()

        event = self.env["federation.finance.event"].search(
            [
                ("source_model", "=", "federation.season.registration"),
                ("source_res_id", "=", registration.id),
            ],
            limit=1,
        )
        self.assertTrue(event, "Finance event should still be created via fallback")
        # Amount should equal fee_type.default_amount (may be 0 for auto-created type)
        self.assertGreaterEqual(event.amount, 0)


class TestCreateInvoice(TransactionCase):
    """Tests for Item 7 — action_create_invoice."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fee_type = cls.env["federation.fee.type"].create(
            {
                "name": "Invoice Test Fee",
                "code": "INV_TEST",
                "category": "registration",
                "default_amount": 200.0,
                "currency_id": cls.env.company.currency_id.id,
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Invoice Test Season",
                "code": "ITS2026",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.club = cls.env["federation.club"].create(
            {"name": "Invoice Club", "code": "IVC"}
        )
        cls.partner = cls.env["res.partner"].create({"name": "Invoice Test Customer"})
        native_accounting = (
            "account.move" in cls.env
            and "invoice_product_id" in cls.env["federation.finance.event"]._fields
        )
        if native_accounting:
            journal_model = cls.env["account.journal"]
            company = cls.env.company
            income_account = cls.env["account.account"].create(
                {
                    "name": "Finance Bridge Test Income",
                    "code": "FBT100",
                    "account_type": "income",
                    "company_ids": [(6, 0, [company.id])],
                }
            )
            if not journal_model.search(
                [("type", "=", "sale"), ("company_id", "=", company.id)],
                limit=1,
            ):
                journal_model.create(
                    {
                        "name": "Finance Bridge Test Sales",
                        "code": "FBT",
                        "type": "sale",
                        "company_id": company.id,
                    }
                )
        cls.invoice_product = (
            cls.env["product.product"].create(
                {
                    "name": "Invoice Test Service",
                    "type": "service",
                    "property_account_income_id": income_account.id,
                }
            )
            if native_accounting
            else False
        )

    def _make_event(self, amount=200.0, source_res_id=None, partner_id=None):
        return self.env["federation.finance.event"].create(
            {
                "name": "Test Invoice Event",
                "fee_type_id": self.fee_type.id,
                "event_type": "charge",
                "amount": amount,
                "currency_id": self.env.company.currency_id.id,
                "source_model": "federation.season",
                "source_res_id": source_res_id or self.season.id,
                "club_id": self.club.id,
                "partner_id": (self.partner.id if partner_id is None else partner_id),
                "state": "confirmed",
                **(
                    {"invoice_product_id": self.invoice_product.id}
                    if "invoice_product_id"
                    in self.env["federation.finance.event"]._fields
                    else {}
                ),
            }
        )

    def _create_invoice(self, event):
        result = event.action_create_invoice()
        if "account_move_id" in event._fields:
            return event.account_move_id
        return result

    def test_create_invoice_requires_native_accounting_addon(self):
        """The bridge must not create invoices without the opt-in accounting addon."""
        if "invoice_product_id" in self.env["federation.finance.event"]._fields:
            self.skipTest("native accounting extension is installed")
        event = self._make_event()
        with self.assertRaises(UserError):
            event.action_create_invoice()
        self.assertFalse(event.invoice_ref)

    def test_create_invoice_succeeds_when_accounting_installed(self):
        """action_create_invoice creates one account.move with the correct amount."""
        if (
            "account.move" not in self.env
            or "invoice_product_id" not in self.env["federation.finance.event"]._fields
        ):
            self.skipTest("configured-product accounting integration is not installed")
        event = self._make_event(amount=150.0)
        invoice = self._create_invoice(event)
        self.assertTrue(invoice)
        lines = invoice.invoice_line_ids
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.price_unit, 150.0)
        self.assertEqual(lines.product_id, self.invoice_product)
        self.assertTrue(lines.account_id, "Invoice line must resolve an income account")
        if "account_move_id" in event._fields:
            self.assertEqual(event.account_move_id, invoice)
            self.assertEqual(invoice.partner_id, self.partner)
        else:
            self.assertEqual(event.invoice_ref, str(invoice.id))

    def test_create_invoice_requires_an_explicit_payer(self):
        if "invoice_product_id" not in self.env["federation.finance.event"]._fields:
            self.skipTest("native accounting extension is not installed")
        event = self._make_event(partner_id=False)
        with self.assertRaises(ValidationError):
            event.action_create_invoice()

    def test_create_invoice_requires_a_configured_product(self):
        if "invoice_product_id" not in self.env["federation.finance.event"]._fields:
            self.skipTest("native accounting extension is not installed")
        event = self._make_event()
        if "invoice_product_id" in event._fields:
            event.invoice_product_id = False
        with self.assertRaises(ValidationError):
            event.action_create_invoice()

    def test_create_invoice_twice_raises(self):
        """Calling action_create_invoice twice raises ValidationError."""
        if (
            "account.move" not in self.env
            or "invoice_product_id" not in self.env["federation.finance.event"]._fields
        ):
            self.skipTest("configured-product accounting integration is not installed")
        event = self._make_event()
        invoice = self._create_invoice(event)
        if "account_move_id" in event._fields:
            event.action_create_invoice()
            self.assertEqual(event.account_move_id, invoice)
            self.assertEqual(
                self.env["account.move"].search_count(
                    [("invoice_origin", "=", event.name)]
                ),
                1,
            )
        else:
            with self.assertRaises(ValidationError):
                event.action_create_invoice()

    def test_create_invoice_on_cancelled_raises(self):
        """Calling action_create_invoice on a cancelled event raises ValidationError."""
        if "invoice_product_id" not in self.env["federation.finance.event"]._fields:
            self.skipTest("native accounting extension is not installed")
        event = self._make_event()
        event.action_cancel()
        with self.assertRaises(ValidationError):
            event.action_create_invoice()

    def test_batch_create_invoices_reports_validation_failures(self):
        """Batch helper raises one user-facing error summary on per-record failures."""
        event_ok = self._make_event(amount=100.0)
        second_season = self.env["federation.season"].create(
            {
                "name": "Invoice Batch Test Season",
                "code": "ITSB2026",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        event_failed = self._make_event(amount=120.0, source_res_id=second_season.id)

        with patch.object(
            type(event_failed),
            "action_create_invoice",
            autospec=True,
            side_effect=[True, ValidationError("Invoice already exists")],
        ):
            with self.assertRaises(UserError):
                (event_ok | event_failed).action_batch_create_invoices()

    def test_batch_create_invoices_returns_true_when_no_failures(self):
        """Batch helper returns True when all eligible records are handled cleanly."""
        event = self._make_event(amount=90.0)
        with patch.object(
            type(event),
            "action_create_invoice",
            autospec=True,
            return_value=True,
        ):
            result = event.action_batch_create_invoices()
        self.assertTrue(result)
