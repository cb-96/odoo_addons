from odoo.tests import TransactionCase
from odoo.exceptions import ValidationError
from odoo.addons.sports_federation_governance.workflow_states import (
    OVERRIDE_DECISION_SELECTION,
    OVERRIDE_REQUEST_STATE_APPROVED,
    OVERRIDE_REQUEST_STATE_CLOSED,
    OVERRIDE_REQUEST_STATE_DRAFT,
    OVERRIDE_REQUEST_STATE_IMPLEMENTED,
    OVERRIDE_REQUEST_STATE_REJECTED,
    OVERRIDE_REQUEST_STATE_SELECTION,
    OVERRIDE_REQUEST_STATE_SUBMITTED,
)


class TestGovernance(TransactionCase):
    """Test cases for governance module."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        # Create test user
        cls.user = cls.env.ref("base.user_admin")

    def test_create_override_request(self):
        """Test creating an override request."""
        request = self.env["federation.override.request"].create(
            {
                "name": "Test Request",
                "request_type": "manual_seeding",
                "target_model": "federation.tournament",
                "target_res_id": 1,
                "reason": "Test reason for override",
            }
        )
        self.assertTrue(request.id)
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_DRAFT)
        self.assertEqual(request.requested_by_id, self.env.user)

    def test_override_models_use_shared_state_selections(self):
        """Governance workflow selections should reuse the shared helper module."""
        self.assertEqual(
            self.env["federation.override.request"].STATE_SELECTION,
            OVERRIDE_REQUEST_STATE_SELECTION,
        )
        self.assertEqual(
            self.env["federation.override.decision"].DECISION_SELECTION,
            OVERRIDE_DECISION_SELECTION,
        )

    def test_submit_override_request(self):
        """Test submitting an override request."""
        request = self.env["federation.override.request"].create(
            {
                "name": "Test Request",
                "request_type": "manual_seeding",
                "target_model": "federation.tournament",
                "target_res_id": 1,
                "reason": "Test reason",
            }
        )
        request.action_submit()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_SUBMITTED)

    def test_withdraw_returns_submitted_request_to_draft(self):
        """Test withdrawing returns a submitted request to draft only."""
        request = self.env["federation.override.request"].create(
            {
                "name": "Withdraw Request",
                "request_type": "manual_seeding",
                "target_model": "federation.tournament",
                "target_res_id": 1,
                "reason": "Need to revise the override before review.",
            }
        )

        with self.assertRaises(ValidationError):
            request.action_withdraw()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_DRAFT)

        request.action_submit()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_SUBMITTED)

        request.action_withdraw()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_DRAFT)

    def test_approve_creates_decision(self):
        """Test approving creates a decision record."""
        request = self.env["federation.override.request"].create(
            {
                "name": "Test Request",
                "request_type": "eligibility_waiver",
                "target_model": "federation.player",
                "target_res_id": 1,
                "reason": "Test reason",
            }
        )
        request.action_submit()
        request.action_approve()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_APPROVED)
        self.assertTrue(request.decision_ids)
        self.assertEqual(
            request.decision_ids[0].decision, OVERRIDE_REQUEST_STATE_APPROVED
        )

    def test_reject_creates_decision(self):
        """Test rejecting creates a decision record."""
        request = self.env["federation.override.request"].create(
            {
                "name": "Test Request",
                "request_type": "late_registration",
                "target_model": "federation.team",
                "target_res_id": 1,
                "reason": "Test reason",
            }
        )
        request.action_submit()
        request.action_reject()
        self.assertEqual(request.state, OVERRIDE_REQUEST_STATE_REJECTED)
        self.assertTrue(request.decision_ids)
        self.assertEqual(
            request.decision_ids[0].decision, OVERRIDE_REQUEST_STATE_REJECTED
        )

    def test_mark_implemented(self):
        """Test marking request as implemented."""
        request = self.env["federation.override.request"].create(
            {
                "name": "Test Request",
                "request_type": "result_correction",
                "target_model": "federation.match",
                "target_res_id": 1,
                "reason": "Test reason",
            }
        )
        request.action_submit()
        request.action_approve()
        request.action_mark_implemented()
        self.assertEqual(request.state, "implemented")
        self.assertTrue(request.outcome_ids)
        self.assertEqual(request.outcome_ids[0].outcome, "implemented")

    def test_override_outcome_records_request_snapshot(self):
        """Test that override outcome records request snapshot."""
        request = self.env["federation.override.request"].create(
            {
                "name": "Tracked Request",
                "request_type": "standing_adjustment",
                "target_model": "federation.tournament",
                "target_res_id": 4,
                "reason": "Track Year 4 outcome logging.",
            }
        )

        outcome = self.env["federation.override.outcome"].create(
            {
                "request_id": request.id,
                "outcome": "effective",
                "note": "The override achieved the intended effect.",
            }
        )

        self.assertEqual(outcome.request_type, "standing_adjustment")
        self.assertEqual(outcome.target_model, "federation.tournament")
        self.assertEqual(outcome.target_res_id, 4)
        self.assertEqual(outcome.request_state, OVERRIDE_REQUEST_STATE_DRAFT)

    def test_target_validation(self):
        """Test target validation constraints."""
        # Test empty target_model
        with self.assertRaises(ValidationError):
            self.env["federation.override.request"].create(
                {
                    "name": "Test Request",
                    "request_type": "manual_seeding",
                    "target_model": "",
                    "target_res_id": 1,
                    "reason": "Test reason",
                }
            )

        # Test target_res_id <= 0
        with self.assertRaises(ValidationError):
            self.env["federation.override.request"].create(
                {
                    "name": "Test Request",
                    "request_type": "manual_seeding",
                    "target_model": "federation.tournament",
                    "target_res_id": 0,
                    "reason": "Test reason",
                }
            )

    def test_empty_reason_validation(self):
        """Test empty reason validation."""
        with self.assertRaises(ValidationError):
            self.env["federation.override.request"].create(
                {
                    "name": "Test Request",
                    "request_type": "manual_seeding",
                    "target_model": "federation.tournament",
                    "target_res_id": 1,
                    "reason": "",
                }
            )

    # --- Edge-case tests ---

    def _make_request(self, **extra):
        """Create a minimal override request."""
        vals = {
            "name": "Edge Case Request",
            "request_type": "manual_seeding",
            "target_model": "federation.tournament",
            "target_res_id": 1,
            "reason": "Edge case test reason.",
        }
        vals.update(extra)
        return self.env["federation.override.request"].create(vals)

    def test_close_after_rejection(self):
        """Rejected request can be closed; closed request cannot be closed again."""
        req = self._make_request()
        req.action_submit()
        req.action_reject()
        self.assertEqual(req.state, OVERRIDE_REQUEST_STATE_REJECTED)
        req.action_close()
        self.assertEqual(req.state, OVERRIDE_REQUEST_STATE_CLOSED)
        with self.assertRaises(ValidationError):
            req.action_close()

    def test_close_after_implementation(self):
        """Implemented request can be closed; draft/submitted/approved cannot."""
        req = self._make_request()
        req.action_submit()
        req.action_approve()
        req.action_mark_implemented()
        req.action_close()
        self.assertEqual(req.state, OVERRIDE_REQUEST_STATE_CLOSED)

    def test_close_guard_draft_and_approved_blocked(self):
        """Draft and approved requests cannot be closed."""
        req_draft = self._make_request()
        with self.assertRaises(ValidationError):
            req_draft.action_close()

        req_approved = self._make_request()
        req_approved.action_submit()
        req_approved.action_approve()
        with self.assertRaises(ValidationError):
            req_approved.action_close()

    def test_implement_guard_requires_approved_state(self):
        """action_mark_implemented raises for draft, submitted, and rejected states."""
        req = self._make_request()
        with self.assertRaises(ValidationError):
            req.action_mark_implemented()

        req.action_submit()
        with self.assertRaises(ValidationError):
            req.action_mark_implemented()

        req.action_reject()
        with self.assertRaises(ValidationError):
            req.action_mark_implemented()

    def test_submit_guard_blocks_non_draft(self):
        """action_submit raises if the request is already submitted or approved."""
        req = self._make_request()
        req.action_submit()
        with self.assertRaises(ValidationError):
            req.action_submit()

        req.action_approve()
        with self.assertRaises(ValidationError):
            req.action_submit()

    def test_implementation_note_recorded_in_outcome(self):
        """Implementation note is captured in the outcome record when provided."""
        req = self._make_request(
            implementation_note="Manually seeded bracket accepted."
        )
        req.action_submit()
        req.action_approve()
        req.action_mark_implemented()
        self.assertTrue(req.outcome_ids)
        self.assertIn("Manually seeded bracket accepted.", req.outcome_ids[0].note)

    def test_whitespace_only_reason_is_rejected(self):
        """Reason consisting only of whitespace must fail validation."""
        with self.assertRaises(ValidationError):
            self._make_request(reason="   ")

    def test_full_lifecycle_draft_to_closed(self):
        """Full happy-path: draft → submit → approve → implement → close."""
        req = self._make_request()
        self.assertEqual(req.state, OVERRIDE_REQUEST_STATE_DRAFT)
        req.action_submit()
        self.assertEqual(req.state, OVERRIDE_REQUEST_STATE_SUBMITTED)
        req.action_approve()
        self.assertEqual(req.state, OVERRIDE_REQUEST_STATE_APPROVED)
        req.action_mark_implemented()
        self.assertEqual(req.state, OVERRIDE_REQUEST_STATE_IMPLEMENTED)
        req.action_close()
        self.assertEqual(req.state, OVERRIDE_REQUEST_STATE_CLOSED)
        # Verify decision and outcome records
        self.assertEqual(len(req.decision_ids), 1)
        self.assertEqual(len(req.outcome_ids), 1)
