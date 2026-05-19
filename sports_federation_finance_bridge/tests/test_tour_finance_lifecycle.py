"""Tour T-08: Finance Events — Lifecycle and Auto-Creation Triggers

Walks the full finance event state machine and idempotent creation:
  1. Create fee type catalogue entries
  2. Create a finance event directly (charge) → draft
  3. Confirm the event → 'confirmed'
  4. Settle the event → 'settled'
  5. Create a second event and cancel it → 'cancelled' (cannot be settled)
  6. Use create_from_source() — idempotent: second call returns same record
  7. Mark exported → handoff_state = 'exported'
  8. Mark reconciled → handoff_state = 'reconciled'

Key invariants verified:
- State transitions: draft → confirmed → settled
- Cancelled events cannot be settled (raises ValidationError or ignored)
- create_from_source() is idempotent (same external_ref is skipped)
- handoff workflow: pending_export → exported → reconciled
"""

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestTourFinanceLifecycle(TransactionCase):
    """T-08: Finance event lifecycle tour."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.club = cls.env["federation.club"].create(
            {"name": "Finance Tour Club", "code": "FTC26"}
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Finance Tour Season",
                "code": "FTS26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )

        # Fee types covering all categories
        cls.fee_registration = cls.env["federation.fee.type"].create(
            {
                "name": "Tour Registration Fee",
                "code": "TOUREG",
                "category": "registration",
                "default_amount": 150.00,
            }
        )
        cls.fee_fine = cls.env["federation.fee.type"].create(
            {
                "name": "Tour Fine",
                "code": "TOUFIN",
                "category": "fine",
                "default_amount": 100.00,
            }
        )

    def test_finance_event_full_lifecycle(self):
        """Finance events: draft → confirmed → settled; cancel; idempotent create; handoff."""

        # STEP 1: Create a charge event manually
        event = self.env["federation.finance.event"].create(
            {
                "name": "Tour Registration 2026",
                "fee_type_id": self.fee_registration.id,
                "event_type": "charge",
                "amount": 150.00,
                "source_model": "federation.club",
                "source_res_id": self.club.id,
                "club_id": self.club.id,
                "season_id": self.season.id,
            }
        )
        self.assertEqual(event.state, "draft")
        self.assertEqual(event.handoff_state, "pending_export")

        # STEP 2: Confirm → immutable amounts
        event.action_confirm()
        self.assertEqual(event.state, "confirmed")

        # STEP 3: Settle
        event.action_settle()
        self.assertEqual(event.state, "settled")

        # STEP 4: Create a second event and cancel it
        event2 = self.env["federation.finance.event"].create(
            {
                "name": "Tour Fine — Contested",
                "fee_type_id": self.fee_fine.id,
                "event_type": "charge",
                "amount": 100.00,
                "source_model": "federation.club",
                "source_res_id": self.club.id,
                "club_id": self.club.id,
            }
        )
        event2.action_cancel()
        self.assertEqual(event2.state, "cancelled")

        # Cancelled events cannot be settled
        with self.assertRaises(Exception):
            event2.action_settle()

        # STEP 5: create_from_source() — idempotent
        src_event = self.env["federation.finance.event"].create_from_source(
            source_record=self.club,
            fee_type=self.fee_registration,
        )
        self.assertTrue(src_event.id)
        self.assertEqual(src_event.source_model, "federation.club")
        self.assertEqual(src_event.source_res_id, self.club.id)

        # Second call with same source+fee_type is idempotent
        src_event_again = self.env["federation.finance.event"].create_from_source(
            source_record=self.club,
            fee_type=self.fee_registration,
        )
        self.assertEqual(src_event_again.id, src_event.id)

        # STEP 6: Handoff workflow on the settled first event
        event.action_mark_exported()
        self.assertEqual(event.handoff_state, "exported")

        event.action_mark_reconciled()
        self.assertEqual(event.handoff_state, "reconciled")
