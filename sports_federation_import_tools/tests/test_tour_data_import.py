"""Tour T-12: Data Import — Bulk Club Import with Dry-Run and Approval Governance

Walks the full import governance workflow for a CSV club import:
  1. Parse CSV in dry-run mode — no records created
  2. Request approval → job enters 'awaiting_approval'
  3. Approve the job
  4. Execute live import → records created, job reaches 'completed'
  5. Verify imported record exists in the database
  6. Demonstrate idempotency guard: file change invalidates approval

Key invariants verified:
- dry_run=True: parse succeeds, zero DB records created
- action_request_approval() creates a governance job in 'awaiting_approval'
- Live run before approval raises ValidationError
- Post-approval live run creates the expected records
- Changing the file after approval invalidates the governance job
"""

import base64

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


def _csv(content):
    return base64.b64encode(content.encode("utf-8"))


class TestTourDataImport(TransactionCase):
    """T-12: Data import tour — CSV clubs with governance approval."""

    def test_import_clubs_dry_run_then_live(self):
        """CSV import: dry run → request approval → approve → live import."""

        csv_content = (
            "name;code;email;phone;city\n"
            "Tour Import Club A;TICA;tica@example.com;555-001;TourCity\n"
            "Tour Import Club B;TICB;ticb@example.com;555-002;TourCity\n"
        )
        wizard = self.env["federation.import.clubs.wizard"].create(
            {
                "upload_file": _csv(csv_content),
                "dry_run": True,
            }
        )

        # STEP 1: Dry run — parse without creating records
        wizard.action_parse_and_import()
        self.assertEqual(wizard.success_count, 2)
        self.assertEqual(wizard.error_count, 0)
        self.assertFalse(self.env["federation.club"].search([("code", "=", "TICA")]))

        # STEP 2: Request approval → governance job created
        wizard.action_request_approval()
        self.assertTrue(wizard.governance_job_id)
        self.assertEqual(wizard.governance_job_id.state, "awaiting_approval")

        # STEP 3: Live run without approval raises
        wizard.dry_run = False
        with self.assertRaises(ValidationError):
            wizard.action_parse_and_import()

        # STEP 4: Approve the job
        wizard.action_approve_import()
        self.assertEqual(wizard.governance_job_id.state, "approved")

        # STEP 5: Live import — records are created
        wizard.action_parse_and_import()
        self.assertEqual(wizard.governance_job_id.state, "completed")

        club_a = self.env["federation.club"].search([("code", "=", "TICA")], limit=1)
        club_b = self.env["federation.club"].search([("code", "=", "TICB")], limit=1)
        self.assertTrue(club_a)
        self.assertTrue(club_b)

    def test_import_approval_invalidated_by_file_change(self):
        """Changing the upload file after approval invalidates the governance job."""

        csv_initial = "name;code\nTour Change Club;TCC01"
        wizard = self.env["federation.import.clubs.wizard"].create(
            {
                "upload_file": _csv(csv_initial),
                "dry_run": True,
            }
        )
        wizard.action_parse_and_import()
        wizard.action_request_approval()
        wizard.action_approve_import()

        # Change file after approval
        wizard.write(
            {
                "upload_file": _csv("name;code\nChanged Club;TCC02"),
                "dry_run": False,
            }
        )
        with self.assertRaises(ValidationError):
            wizard.action_parse_and_import()
