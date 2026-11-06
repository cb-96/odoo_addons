from odoo.tests import TransactionCase, tagged

from .test_lifecycle import FamilyFixture


@tagged("post_install", "-at_install", "sf_member_services")
class TestRenewalProgress(FamilyFixture, TransactionCase):
    def _renewal(self):
        result = (
            self.memberships[0].with_user(self.guardian)._renew(self.next_season.id)
        )
        return self.env["federation.person.membership"].browse(result)

    def test_an_original_membership_is_not_a_renewal(self):
        self.assertEqual(self.memberships[0].renewal_step, "none")
        self.assertFalse(self.memberships[0].renewal_blockers)

    def test_a_new_renewal_waits_for_the_review_of_changes(self):
        renewal = self._renewal()
        self.assertEqual(renewal.renewal_step, "initiated")
        self.assertIn("review", renewal.renewal_blockers.lower())

    def test_a_reviewed_renewal_without_documents_is_ready(self):
        renewal = self._renewal()
        renewal.with_user(self.reviewer).write({"review_note": "Changes reviewed"})
        self.assertEqual(renewal.renewal_step, "ready")
        self.assertFalse(renewal.renewal_blockers)

    def test_an_unverified_required_document_is_a_compliance_blocker(self):
        self.document(
            membership_id=self.memberships[0].id, required_for_activation=True
        )
        renewal = self._renewal()
        renewal.with_user(self.reviewer).write({"review_note": "Changes reviewed"})
        self.assertEqual(renewal.renewal_step, "compliance")
        self.assertIn("document", renewal.renewal_blockers)

    def test_an_activated_renewal_is_approved(self):
        renewal = self._renewal()
        renewal.with_user(self.reviewer).write({"review_note": "Changes reviewed"})
        renewal.with_user(self.reviewer).action_activate()
        self.assertEqual(renewal.renewal_step, "approved")

    def test_the_renewal_reuses_the_same_identity(self):
        renewal = self._renewal()
        self.assertEqual(renewal.person_id, self.memberships[0].person_id)

    def test_progress_changes_nothing(self):
        renewal = self._renewal()
        before = (renewal.state, renewal.review_note, renewal.lifecycle_revision)
        renewal.renewal_step  # noqa: B018 - reading the projection
        renewal.renewal_blockers  # noqa: B018
        renewal.invalidate_recordset()
        self.assertEqual(
            (renewal.state, renewal.review_note, renewal.lifecycle_revision), before
        )
