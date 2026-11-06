from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.evidence_retention import (
    RETENTION_PARAMETER,
    evidence_retention_days_from_value,
)
from .test_lifecycle import FamilyFixture

REASON = "Case 2026-114 reviewed by the privacy officer"


@tagged(
    "post_install",
    "-at_install",
    "sf_member_lifecycle",
    "sf_member_evidence_retention",
)
class TestMemberEvidenceRetention(FamilyFixture, TransactionCase):
    def _replaced_document(self):
        doc = self.document()
        self.upload(doc)
        doc.review_note = "Replacement required"
        doc.action_return()
        self.upload(doc, b"%PDF-1.4 second evidence")
        revisions = self.env["federation.member.evidence.revision"].search(
            [("request_id", "=", doc.id)], order="revision"
        )
        self.assertEqual(len(revisions), 2)
        return doc, revisions[0], revisions[1]

    def _age(self, revisions, days=400):
        old = fields.Datetime.now() - timedelta(days=days)
        self.env.cr.execute(
            "UPDATE federation_member_evidence_revision "
            "SET create_date = %s WHERE id IN %s",
            (old, tuple(revisions.ids)),
        )
        revisions.invalidate_recordset(["create_date"])

    def _wizard(self, revisions, operation, **values):
        return (
            self.env["federation.member.evidence.governance.wizard"]
            .with_user(self.reviewer)
            .create(
                {
                    "revision_ids": [(6, 0, revisions.ids)],
                    "operation": operation,
                    "reason": REASON,
                    **values,
                }
            )
        )

    def test_parameter_parsing(self):
        self.assertEqual(evidence_retention_days_from_value(""), (0, False))
        self.assertEqual(evidence_retention_days_from_value("0"), (0, False))
        self.assertEqual(evidence_retention_days_from_value("730"), (730, False))
        days, problem = evidence_retention_days_from_value("two years")
        self.assertEqual(days, 0)
        self.assertTrue(problem)

    def test_direct_edit_and_delete_remain_blocked(self):
        _doc, first, _second = self._replaced_document()
        with self.assertRaises(AccessError):
            first.sudo().write({"legal_hold": True})
        with self.assertRaises(AccessError):
            first.sudo().unlink()

    def test_legal_hold_is_recorded_and_released_with_reasons(self):
        doc, first, _second = self._replaced_document()
        self._wizard(first, "hold").action_apply()
        self.assertTrue(first.legal_hold)
        self.assertEqual(first.legal_hold_reason, REASON)
        self.assertEqual(first.legal_hold_by_id, self.reviewer)
        self.assertIn("Legal hold placed", doc.message_ids[0].body)
        self._wizard(first, "release").action_apply()
        self.assertFalse(first.legal_hold)
        self.assertIn("Legal hold released", doc.message_ids[0].body)

    def test_short_reason_is_refused(self):
        _doc, first, _second = self._replaced_document()
        with self.assertRaises(ValidationError):
            self._wizard(first, "hold", reason="because").action_apply()

    def test_portal_user_cannot_hold_or_erase(self):
        _doc, first, _second = self._replaced_document()
        with self.assertRaises(AccessError):
            first.with_user(self.guardian)._set_legal_hold(REASON)
        with self.assertRaises(AccessError):
            first.with_user(self.guardian)._erase(REASON)

    def test_erasure_requires_confirmation_and_respects_legal_hold(self):
        doc, first, second = self._replaced_document()
        with self.assertRaises(ValidationError):
            self._wizard(first, "erase").action_apply()
        self._wizard(first, "hold").action_apply()
        with self.assertRaises(ValidationError):
            self._wizard(first | second, "erase", confirm_erasure=True).action_apply()
        self.assertTrue(first.exists() and second.exists())

        self._wizard(second, "erase", confirm_erasure=True).action_apply()
        self.assertFalse(second.exists())
        self.assertTrue(first.exists())
        self.assertIn("erased", doc.message_ids[0].body)
        evidence = self.env["federation.retention.evidence"].sudo().search(
            [("policy", "=", "member_evidence_erasure")], order="id desc", limit=1
        )
        self.assertEqual(evidence.deleted_count, 1)
        self.assertEqual(evidence.operator_message, REASON)

    def test_nothing_is_deleted_without_a_configured_period(self):
        _doc, first, second = self._replaced_document()
        self._age(first | second)
        self.env["ir.config_parameter"].sudo().set_param(RETENTION_PARAMETER, "")
        self.env["federation.member.evidence.revision"]._cron_purge_evidence()
        self.assertTrue(first.exists() and second.exists())

    def test_schedule_removes_only_old_replaced_unheld_revisions(self):
        doc, first, second = self._replaced_document()
        self.assertEqual(doc.document_revision, second.revision)
        self._age(first | second)
        self.env["ir.config_parameter"].sudo().set_param(RETENTION_PARAMETER, "365")

        self.env["federation.member.evidence.revision"]._cron_purge_evidence()

        self.assertFalse(first.exists(), "the replaced revision is past the period")
        self.assertTrue(
            second.exists(), "the current revision of an open request stays"
        )
        evidence = self.env["federation.retention.evidence"].sudo().search(
            [("policy", "=", "member_evidence_revisions")], order="id desc", limit=1
        )
        self.assertEqual(evidence.status, "passed")
        self.assertEqual(evidence.deleted_count, 1)

    def test_schedule_keeps_held_and_recent_revisions(self):
        _doc, first, second = self._replaced_document()
        self._wizard(first, "hold").action_apply()
        self._age(first)
        self.env["ir.config_parameter"].sudo().set_param(RETENTION_PARAMETER, "365")

        self.env["federation.member.evidence.revision"]._cron_purge_evidence()

        self.assertTrue(first.exists(), "legal hold wins over the retention period")
        self.assertTrue(second.exists(), "recent revisions stay")
        evidence = self.env["federation.retention.evidence"].sudo().search(
            [("policy", "=", "member_evidence_revisions")], order="id desc", limit=1
        )
        self.assertEqual(evidence.skipped_count, 1)
