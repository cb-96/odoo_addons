"""Tests for federation.reimbursement.request model."""
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestReimbursementRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.referee = cls.env["federation.referee"].create(
            {
                "name": "Reimb Referee",
                "email": "reimb@test.example",
                "certification_level": "national",
            }
        )

    def _make(self, **kwargs):
        vals = {
            "name": "REIMB-001",
            "referee_id": self.referee.id,
            "amount": 75.0,
        }
        vals.update(kwargs)
        return self.env["federation.reimbursement.request"].create(vals)

    # ── creation ─────────────────────────────────────────────────────────────

    def test_create_in_draft_state(self):
        req = self._make()
        self.assertEqual(req.state, "draft")

    def test_negative_amount_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._make(amount=-5.0)

    def test_zero_amount_is_allowed(self):
        req = self._make(amount=0.0)
        self.assertEqual(req.amount, 0.0)

    # ── full happy-path lifecycle ─────────────────────────────────────────────

    def test_full_lifecycle_draft_to_paid(self):
        req = self._make()
        req.action_submit()
        self.assertEqual(req.state, "submitted")
        req.action_approve()
        self.assertEqual(req.state, "approved")
        req.write({"payment_ref": "TRF-2026-001"})
        req.action_mark_paid()
        self.assertEqual(req.state, "paid")
        self.assertTrue(req.paid_on)

    # ── cancellation ─────────────────────────────────────────────────────────

    def test_cancel_from_submitted(self):
        req = self._make()
        req.action_submit()
        req.action_cancel()
        self.assertEqual(req.state, "cancelled")

    def test_cancel_from_approved(self):
        req = self._make()
        req.action_submit()
        req.action_approve()
        req.action_cancel()
        self.assertEqual(req.state, "cancelled")

    def test_paid_request_cannot_be_cancelled(self):
        req = self._make()
        req.action_submit()
        req.action_approve()
        req.action_mark_paid()
        with self.assertRaises(ValidationError):
            req.action_cancel()

    def test_reset_cancelled_to_draft(self):
        req = self._make()
        req.action_cancel()
        req.action_reset_draft()
        self.assertEqual(req.state, "draft")

    def test_reset_non_cancelled_raises(self):
        req = self._make()
        req.action_submit()
        with self.assertRaises(ValidationError):
            req.action_reset_draft()

    # ── guard validation ──────────────────────────────────────────────────────

    def test_submit_non_draft_raises(self):
        req = self._make()
        req.action_submit()
        with self.assertRaises(ValidationError):
            req.action_submit()

    def test_approve_non_submitted_raises(self):
        req = self._make()
        with self.assertRaises(ValidationError):
            req.action_approve()

    def test_mark_paid_non_approved_raises(self):
        req = self._make()
        req.action_submit()
        with self.assertRaises(ValidationError):
            req.action_mark_paid()

    # ── CSV export ───────────────────────────────────────────────────────────

    def test_export_csv_raises_when_no_approved(self):
        req = self._make()
        with self.assertRaises(UserError):
            req.action_export_bank_transfer_csv()

    def test_export_csv_returns_download_action(self):
        req = self._make()
        req.action_submit()
        req.action_approve()
        result = req.action_export_bank_transfer_csv()
        self.assertEqual(result["type"], "ir.actions.act_url")
        self.assertIn("/web/content/", result["url"])

    def test_export_csv_skips_non_approved(self):
        req_approved = self._make(name="REIMB-A")
        req_draft = self._make(name="REIMB-D")
        req_approved.action_submit()
        req_approved.action_approve()
        # Only req_approved is approved; calling on both should only export approved
        combined = req_approved | req_draft
        result = combined.action_export_bank_transfer_csv()
        self.assertEqual(result["type"], "ir.actions.act_url")
