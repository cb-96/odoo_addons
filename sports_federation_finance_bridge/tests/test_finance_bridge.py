from odoo import fields
from odoo.tests import TransactionCase
from odoo.exceptions import ValidationError


class TestFinanceBridge(TransactionCase):
    """Test cases for finance bridge module."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        # Create test club
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Test Club",
                "code": "TC001",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Finance Season",
                "code": "FIN2026",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Finance Team",
                "club_id": cls.club.id,
                "code": "FINTEAM",
            }
        )

    def test_create_fee_type(self):
        """Test creating a fee type."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Test Fee",
                "code": "TESTFEE",
                "category": "registration",
                "default_amount": 100.00,
            }
        )
        self.assertTrue(fee_type.id)
        self.assertEqual(fee_type.name, "Test Fee")
        self.assertEqual(fee_type.code, "TESTFEE")
        self.assertEqual(fee_type.category, "registration")
        self.assertEqual(fee_type.default_amount, 100.00)

    def test_create_finance_event_directly(self):
        """Test creating a finance event directly."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Test Fee",
                "code": "TESTFEE",
                "category": "registration",
                "default_amount": 100.00,
            }
        )
        event = self.env["federation.finance.event"].create(
            {
                "name": "Test Event",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 100.00,
                "source_model": "federation.club",
                "source_res_id": self.club.id,
                "club_id": self.club.id,
            }
        )
        self.assertTrue(event.id)
        self.assertEqual(event.name, "Test Event")
        self.assertEqual(event.event_type, "charge")
        self.assertEqual(event.amount, 100.00)
        self.assertEqual(event.state, "draft")

    def test_create_finance_event_from_source(self):
        """Test creating a finance event from source record."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Test Fee",
                "code": "TESTFEE",
                "category": "registration",
                "default_amount": 100.00,
            }
        )
        event = self.env["federation.finance.event"].create_from_source(
            source_record=self.club,
            fee_type=fee_type,
        )
        self.assertTrue(event.id)
        self.assertEqual(event.source_model, "federation.club")
        self.assertEqual(event.source_res_id, self.club.id)
        self.assertEqual(event.club_id, self.club)
        self.assertEqual(event.amount, 100.00)
        self.assertEqual(event.external_ref, f"TESTFEE-federation_club-{self.club.id}")

    def test_ensure_finance_event_from_source_is_idempotent(self):
        """Test that ensure finance event from source is idempotent."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Idempotent Fee",
                "code": "IDEMP",
                "category": "registration",
                "default_amount": 90.00,
            }
        )

        event_one = self.env["federation.finance.event"].ensure_from_source(
            self.club,
            fee_type,
            note="First pass",
        )
        event_two = self.env["federation.finance.event"].ensure_from_source(
            self.club,
            fee_type,
            note="Second pass",
        )

        self.assertEqual(event_one, event_two)
        self.assertEqual(
            self.env["federation.finance.event"].search_count(
                [
                    ("fee_type_id", "=", fee_type.id),
                    ("source_model", "=", "federation.club"),
                    ("source_res_id", "=", self.club.id),
                ]
            ),
            1,
        )

    def test_finance_event_amount_validation(self):
        """Test amount validation on finance event."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Test Fee",
                "code": "TESTFEE",
                "category": "registration",
                "default_amount": 100.00,
            }
        )
        with self.assertRaises(ValidationError):
            self.env["federation.finance.event"].create(
                {
                    "name": "Test Event",
                    "fee_type_id": fee_type.id,
                    "event_type": "charge",
                    "amount": -10.00,
                    "source_model": "federation.club",
                    "source_res_id": self.club.id,
                }
            )

    def test_state_transitions(self):
        """Test state transitions on finance event."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Test Fee",
                "code": "TESTFEE",
                "category": "registration",
                "default_amount": 100.00,
            }
        )
        event = self.env["federation.finance.event"].create(
            {
                "name": "Test Event",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 100.00,
                "source_model": "federation.club",
                "source_res_id": self.club.id,
            }
        )
        self.assertEqual(event.state, "draft")

        # Confirm
        event.action_confirm()
        self.assertEqual(event.state, "confirmed")

        # Settle
        event.action_settle()
        self.assertEqual(event.state, "settled")

        event.accounting_batch_ref = "ACC-BATCH-1"
        event.action_mark_exported()
        self.assertEqual(event.handoff_state, "exported")
        self.assertTrue(event.exported_on)
        self.assertTrue(event.exported_by_id)

        event.reconciliation_ref = "RECON-1"
        event.action_mark_reconciled()
        self.assertEqual(event.handoff_state, "reconciled")
        self.assertTrue(event.reconciled_on)
        self.assertTrue(event.reconciled_by_id)

        event.action_close_handoff()
        self.assertEqual(event.handoff_state, "closed")
        self.assertTrue(event.closed_on)
        self.assertTrue(event.closed_by_id)

        # Cannot cancel settled
        with self.assertRaises(ValidationError):
            event.action_cancel()

    def test_reconciliation_requires_export_and_settlement(self):
        """Test that reconciliation requires export and settlement."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Handoff Fee",
                "code": "HANDOFF",
                "category": "registration",
                "default_amount": 125.00,
            }
        )
        event = self.env["federation.finance.event"].create(
            {
                "name": "Handoff Event",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 125.00,
                "source_model": "federation.club",
                "source_res_id": self.club.id,
                "club_id": self.club.id,
            }
        )

        with self.assertRaises(ValidationError):
            event.action_mark_exported()

        event.action_confirm()
        event.action_mark_exported()

        with self.assertRaises(ValidationError):
            event.action_mark_reconciled()

        event.action_settle()
        event.action_mark_reconciled()
        self.assertEqual(event.handoff_state, "reconciled")

    def test_handoff_export_row_includes_contract_fields(self):
        """Test that handoff export row includes contract fields."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Export Fee",
                "code": "EXPFEE",
                "category": "other",
                "default_amount": 60.00,
            }
        )
        event = self.env["federation.finance.event"].create(
            {
                "name": "Exportable Event",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 60.00,
                "source_model": "federation.club",
                "source_res_id": self.club.id,
                "club_id": self.club.id,
                "accounting_batch_ref": "ACC-2026-001",
                "reconciliation_ref": "REC-2026-001",
                "invoice_ref": "INV-2026-001",
                "external_ref": "EXT-2026-001",
            }
        )

        headers = self.env["federation.finance.event"].get_handoff_export_headers()
        row = event.get_handoff_export_row()

        self.assertEqual(
            row[0], self.env["federation.finance.event"].EXPORT_SCHEMA_VERSION
        )
        self.assertEqual(len(row), len(headers))
        self.assertIn("Accounting Batch Ref", headers)
        self.assertIn("Reconciliation Ref", headers)
        self.assertIn("ACC-2026-001", row)
        self.assertIn("REC-2026-001", row)

    def test_handoff_export_batch_paginates_with_stable_cursor(self):
        """Test that handoff exports page newest-first with a resumable cursor."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Paged Export Fee",
                "code": "PAGEDEXP",
                "category": "other",
                "default_amount": 15.00,
            }
        )
        second_club = self.env["federation.club"].create(
            {
                "name": "Second Export Club",
                "code": "TC002",
            }
        )
        third_club = self.env["federation.club"].create(
            {
                "name": "Third Export Club",
                "code": "TC003",
            }
        )
        first = self.env["federation.finance.event"].create(
            {
                "name": "Oldest Export Event",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 15.00,
                "source_model": "federation.club",
                "source_res_id": self.club.id,
                "club_id": self.club.id,
            }
        )
        second = self.env["federation.finance.event"].create(
            {
                "name": "Middle Export Event",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 16.00,
                "source_model": "federation.club",
                "source_res_id": second_club.id,
                "club_id": second_club.id,
            }
        )
        third = self.env["federation.finance.event"].create(
            {
                "name": "Newest Export Event",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 17.00,
                "source_model": "federation.club",
                "source_res_id": third_club.id,
                "club_id": third_club.id,
            }
        )

        first_batch = self.env["federation.finance.event"].get_handoff_export_batch(
            limit=2
        )

        self.assertEqual(first_batch["events"].ids, [third.id, second.id])
        self.assertEqual(
            first_batch["next_cursor"],
            f"{fields.Datetime.to_string(second.create_date)}|{second.id}",
        )
        self.assertTrue(first_batch["has_more"])

        second_batch = self.env["federation.finance.event"].get_handoff_export_batch(
            cursor=first_batch["next_cursor"],
            limit=2,
        )

        self.assertEqual(second_batch["events"].ids, [first.id])
        self.assertFalse(second_batch["has_more"])
        self.assertFalse(second_batch["next_cursor"])

    def test_handoff_export_batch_rejects_invalid_limit(self):
        """Test that cursor exports reject invalid limits."""
        with self.assertRaises(ValidationError):
            self.env["federation.finance.event"].get_handoff_export_batch(limit="0")

    def test_handoff_export_batch_rejects_invalid_cursor(self):
        """Test that cursor exports reject malformed cursors."""
        with self.assertRaises(ValidationError):
            self.env["federation.finance.event"].get_handoff_export_batch(
                cursor="not-a-valid-cursor"
            )

    def test_handoff_export_limit_defaults_when_unspecified(self):
        """Test that cursor exports default to the configured page size."""
        self.assertEqual(
            self.env["federation.finance.event"]._normalize_handoff_export_limit(),
            self.env["federation.finance.event"].HANDOFF_EXPORT_DEFAULT_LIMIT,
        )

    def test_handoff_export_limit_caps_requested_page_size(self):
        """Test that cursor exports clamp oversized page sizes."""
        self.assertEqual(
            self.env["federation.finance.event"]._normalize_handoff_export_limit(
                limit="999"
            ),
            self.env["federation.finance.event"].HANDOFF_EXPORT_MAX_LIMIT,
        )

    def test_finance_event_infers_season_from_source_record(self):
        """Test that finance event infers season from source record."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Season Fee",
                "code": "SEASONFEE",
                "category": "registration",
                "default_amount": 80.00,
            }
        )
        registration = self.env["federation.season.registration"].create(
            {
                "season_id": self.season.id,
                "team_id": self.team.id,
            }
        )

        event = self.env["federation.finance.event"].create_from_source(
            source_record=registration,
            fee_type=fee_type,
        )

        self.assertEqual(event.season_id, self.season)

    def test_season_budget_tracks_actuals_and_variance(self):
        """Test that season budget tracks actuals and variance."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Budget Fee",
                "code": "BUDGETFEE",
                "category": "registration",
                "default_amount": 120.00,
            }
        )
        budget = self.env["federation.season.budget"].create(
            {
                "season_id": self.season.id,
                "fee_type_id": fee_type.id,
                "budget_amount": 300.00,
            }
        )
        confirmed_event = self.env["federation.finance.event"].create(
            {
                "name": "Budget Confirmed",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 125.00,
                "season_id": self.season.id,
                "source_model": "federation.season",
                "source_res_id": self.season.id,
            }
        )
        confirmed_event.action_confirm()
        draft_event = self.env["federation.finance.event"].create(
            {
                "name": "Budget Draft",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 75.00,
                "season_id": self.season.id,
                "source_model": "federation.team",
                "source_res_id": self.team.id,
            }
        )

        budget.invalidate_recordset()
        self.assertEqual(budget.actual_amount, 125.00)
        self.assertEqual(budget.actual_event_count, 1)
        self.assertEqual(budget.variance_amount, -175.00)

        draft_event.action_confirm()
        budget.invalidate_recordset()
        self.assertEqual(budget.actual_amount, 200.00)
        self.assertEqual(budget.actual_event_count, 2)
        self.assertEqual(budget.variance_amount, -100.00)

    def test_cancel_from_draft(self):
        """Test cancelling from draft."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Test Fee",
                "code": "TESTFEE",
                "category": "registration",
                "default_amount": 100.00,
            }
        )
        event = self.env["federation.finance.event"].create(
            {
                "name": "Test Event",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 100.00,
                "source_model": "federation.club",
                "source_res_id": self.club.id,
            }
        )
        event.action_cancel()
        self.assertEqual(event.state, "cancelled")

    def test_cancel_from_confirmed(self):
        """Test cancelling from confirmed."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Test Fee",
                "code": "TESTFEE",
                "category": "registration",
                "default_amount": 100.00,
            }
        )
        event = self.env["federation.finance.event"].create(
            {
                "name": "Test Event",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 100.00,
                "source_model": "federation.club",
                "source_res_id": self.club.id,
            }
        )
        event.action_confirm()
        event.action_cancel()
        self.assertEqual(event.state, "cancelled")
