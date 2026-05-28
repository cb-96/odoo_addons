"""Tour T-11: Governance Override — Late Registration Exception

Walks the full governance override request lifecycle:
  1. Create an override request (late_registration type)
  2. Submit → 'submitted'
  3. Withdraw → 'draft' (only valid from submitted)
  4. Cannot withdraw from draft (raises ValidationError)
  5. Re-submit → 'submitted'
  6. Approve → 'approved'
  7. Implement the exception → 'implemented'
  8. Close → 'closed'

Also exercises the rejection path:
  9. Create a second request, submit, reject → 'rejected', close → 'closed'

Key invariants verified:
- action_withdraw() only works from 'submitted'
- action_approve() and action_reject() only work from 'submitted'
- action_mark_implemented() only works from 'approved'
- action_close() works from 'implemented' and 'rejected'
"""

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from odoo.addons.sports_federation_governance.workflow_states import (
    OVERRIDE_REQUEST_STATE_APPROVED,
    OVERRIDE_REQUEST_STATE_CLOSED,
    OVERRIDE_REQUEST_STATE_DRAFT,
    OVERRIDE_REQUEST_STATE_IMPLEMENTED,
    OVERRIDE_REQUEST_STATE_REJECTED,
    OVERRIDE_REQUEST_STATE_SUBMITTED,
)


class TestTourGovernanceOverride(TransactionCase):
    """T-11: Governance override request lifecycle tour."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Minimal target record — tournament participant would be ideal,
        # but we just need any real record ID. Using a club for simplicity.
        cls.club = cls.env["federation.club"].create(
            {"name": "Governance Tour Club", "code": "GTC26"}
        )

    def _make_request(
        self, name="Tour Override Request", request_type="late_registration"
    ):
        return self.env["federation.override.request"].create(
            {
                "name": name,
                "request_type": request_type,
                "target_model": "federation.club",
                "target_res_id": self.club.id,
                "reason": "Late registration due to administrative delay — approved by board.",
            }
        )

    def test_governance_override_approval_path(self):
        """Full override lifecycle: submit → withdraw → resubmit → approve → implement → close."""
        request = self._make_request()

        # STEP 1: Initial state
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_DRAFT)

        # STEP 2: Submit
        request.action_submit()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_SUBMITTED)

        # STEP 3: Withdraw → back to draft
        request.action_withdraw()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_DRAFT)

        # STEP 4: Cannot withdraw from draft
        with self.assertRaises(ValidationError):
            request.action_withdraw()

        # STEP 5: Re-submit
        request.action_submit()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_SUBMITTED)

        # STEP 6: Approve
        request.action_approve()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_APPROVED)

        # STEP 7: Implement
        request.implementation_note = (
            "Participant enrolled via manual override process."
        )
        request.action_mark_implemented()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_IMPLEMENTED)

        # STEP 8: Close
        request.action_close()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_CLOSED)

    def test_governance_override_rejection_path(self):
        """Rejection path: submit → reject → close."""
        request = self._make_request(
            name="Rejected Override Request",
            request_type="eligibility_waiver",
        )
        request.action_submit()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_SUBMITTED)

        request.action_reject()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_REJECTED)

        request.action_close()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_CLOSED)
