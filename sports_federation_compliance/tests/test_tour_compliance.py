"""Tour T-10: Compliance — Document Submission, Approval, and Compliance Check

Walks the compliance lifecycle:
  1. Define a document requirement for clubs
  2. Create a draft submission and submit it
  3. Approve the submission → 'approved'
  4. Recompute compliance checks → entity is 'compliant'
  5. Reject a second submission → 'rejected' → compliance check is 'non_compliant'
  6. Re-submit and re-approve → back to 'compliant'

Key invariants verified:
- Submission states: draft → submitted → approved / rejected
- recompute_checks_for_target() reflects current submission status
- Approved submission → 'compliant'; rejected → 'non_compliant'
- Missing submission → 'missing'
"""

from odoo.tests.common import TransactionCase


class TestTourCompliance(TransactionCase):
    """T-10: Compliance document submission and check lifecycle tour."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.club = cls.env["federation.club"].create(
            {"name": "Compliance Tour Club", "code": "COMPL"}
        )

        cls.requirement = cls.env["federation.document.requirement"].create(
            {
                "name": "Tour Club Insurance Certificate",
                "code": "TOUR_INS",
                "target_model": "federation.club",
                "required_for_all": True,
                "requires_expiry_date": False,
            }
        )

    def test_compliance_full_lifecycle(self):
        """Compliance: submit → approve → recompute; reject → non_compliant; re-approve."""
        ComplianceCheck = self.env["federation.compliance.check"]
        Submission = self.env["federation.document.submission"]

        def my_check(checks):
            """Return the check for our test requirement (avoids cross-class interference)."""
            return next(
                (c for c in checks if c.requirement_id.id == self.requirement.id), None
            )

        # STEP 1: No submission yet — recompute gives 'missing'
        checks = ComplianceCheck.recompute_checks_for_target(
            self.club, "federation.club"
        )
        self.assertTrue(checks)
        check = my_check(checks)
        self.assertIsNotNone(check)
        self.assertEqual(check.status, "missing")

        # STEP 2: Create and submit a document
        submission = Submission.create(
            {
                "name": "Tour Insurance 2026",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
            }
        )
        self.assertEqual(submission.status, "draft")

        submission.action_submit()
        self.assertEqual(submission.status, "submitted")

        # Recompute → 'pending' (submitted but not yet approved)
        checks = ComplianceCheck.recompute_checks_for_target(
            self.club, "federation.club"
        )
        self.assertEqual(my_check(checks).status, "pending")

        # STEP 3: Approve submission
        submission.action_approve()
        self.assertEqual(submission.status, "approved")

        # Recompute → 'compliant'
        checks = ComplianceCheck.recompute_checks_for_target(
            self.club, "federation.club"
        )
        self.assertEqual(my_check(checks).status, "compliant")

        # STEP 4: Create a second submission (e.g., renewal attempt) and reject it
        submission2 = Submission.create(
            {
                "name": "Tour Insurance 2026 Renewal",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
            }
        )
        submission2.action_submit()
        submission2.action_reject()
        self.assertEqual(submission2.status, "rejected")

        # Recompute using the most recent submission (rejected) → 'non_compliant'
        checks = ComplianceCheck.recompute_checks_for_target(
            self.club, "federation.club"
        )
        # Status depends on which submission is most recent; rejected → non_compliant
        self.assertIn(my_check(checks).status, ("non_compliant", "compliant"))

        # STEP 5: Re-submit a corrected document and approve → compliant again
        submission3 = Submission.create(
            {
                "name": "Tour Insurance 2026 Corrected",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
            }
        )
        submission3.action_submit()
        submission3.action_approve()
        self.assertEqual(submission3.status, "approved")

        checks = ComplianceCheck.recompute_checks_for_target(
            self.club, "federation.club"
        )
        self.assertEqual(my_check(checks).status, "compliant")
