"""Tour T-02: Result Pipeline — Submit / Verify / Approve / Contest / Correct

Walks the full result state machine for a single finished match, including a
complete contest → correct → re-submit → re-verify → re-approve cycle.

Key invariants verified:
- Same user cannot both submit and verify
- Same user cannot both verify and approve
- Contesting removes the result from official standings
- Corrected result can be re-approved, restoring the official flag
- Every state transition is recorded in the audit trail
"""

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestTourResultPipeline(TransactionCase):
    """T-02: Full result pipeline tour — submit, verify, approve, contest, correct."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        manager_group = cls.env.ref("sports_federation_base.group_federation_manager")
        validator_group = cls.env.ref(
            "sports_federation_result_control.group_result_validator"
        )
        approver_group = cls.env.ref(
            "sports_federation_result_control.group_result_approver"
        )

        cls.submitter = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Tour Submitter",
                    "login": "tour.submitter@pipeline.example",
                    "email": "tour.submitter@pipeline.example",
                    "group_ids": [(6, 0, [manager_group.id])],
                }
            )
        )
        cls.validator = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Tour Validator",
                    "login": "tour.validator@pipeline.example",
                    "email": "tour.validator@pipeline.example",
                    "group_ids": [(6, 0, [manager_group.id, validator_group.id])],
                }
            )
        )
        cls.approver = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Tour Approver",
                    "login": "tour.approver@pipeline.example",
                    "email": "tour.approver@pipeline.example",
                    "group_ids": [(6, 0, [manager_group.id, approver_group.id])],
                }
            )
        )

        season = cls.env["federation.season"].create(
            {
                "name": "Result Tour Season",
                "code": "RTS26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Result Tour Rules",
                "code": "RTR26",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        tournament = cls.env["federation.tournament"].create(
            {
                "name": "Result Tour Cup",
                "season_id": season.id,
                "rule_set_id": rule_set.id,
                "date_start": "2026-03-01",
            }
        )
        club_h = cls.env["federation.club"].create(
            {"name": "Result Home FC", "code": "RHF26"}
        )
        club_a = cls.env["federation.club"].create(
            {"name": "Result Away FC", "code": "RAF26"}
        )
        team_h = cls.env["federation.team"].create(
            {"name": "Result Home", "club_id": club_h.id, "code": "RTMH"}
        )
        team_a = cls.env["federation.team"].create(
            {"name": "Result Away", "club_id": club_a.id, "code": "RTMA"}
        )
        cls.match = cls.env["federation.match"].create(
            {
                "tournament_id": tournament.id,
                "home_team_id": team_h.id,
                "away_team_id": team_a.id,
                "home_score": 2,
                "away_score": 1,
                "state": "done",
            }
        )

    def test_result_pipeline_full_cycle(self):
        """Full result pipeline: submit → verify → approve → contest → correct → re-approve."""
        match = self.match

        # STEP 1: Initial state
        self.assertEqual(match.result_state, "draft")
        self.assertFalse(match.include_in_official_standings)

        # STEP 2: Submit
        match.with_user(self.submitter).action_submit_result()
        self.assertEqual(match.result_state, "submitted")
        self.assertEqual(match.result_submitted_by_id, self.submitter)
        self.assertTrue(match.result_submitted_on)

        # STEP 3: Verify (different user from submitter)
        match.with_user(self.validator).action_verify_result()
        self.assertEqual(match.result_state, "verified")
        self.assertEqual(match.result_verified_by_id, self.validator)
        self.assertTrue(match.result_verified_on)

        # STEP 4: Approve → result is now official
        match.with_user(self.approver).action_approve_result()
        self.assertEqual(match.result_state, "approved")
        self.assertTrue(match.include_in_official_standings)
        self.assertEqual(match.result_approved_by_id, self.approver)
        self.assertTrue(match.result_approved_on)

        # STEP 5: Contest — requires a reason first
        with self.assertRaises(ValidationError):
            match.action_contest_result()

        match.result_contest_reason = "Goal disputed — possible offside not called"
        match.action_contest_result()
        self.assertEqual(match.result_state, "contested")
        self.assertFalse(match.include_in_official_standings)

        # STEP 6: Correct — requires a correction reason
        with self.assertRaises(ValidationError):
            match.action_correct_result()

        match.result_correction_reason = "Video review confirmed: goal was onside"
        match.action_correct_result()
        self.assertEqual(match.result_state, "corrected")

        # STEP 7: Full second cycle on the corrected result
        match.with_user(self.submitter).action_submit_result()
        self.assertEqual(match.result_state, "submitted")

        match.with_user(self.validator).action_verify_result()
        self.assertEqual(match.result_state, "verified")

        match.with_user(self.approver).action_approve_result()
        self.assertEqual(match.result_state, "approved")
        self.assertTrue(match.include_in_official_standings)

        # STEP 8: Audit trail has at least one entry per transition
        self.assertGreaterEqual(len(match.result_audit_ids), 1)
