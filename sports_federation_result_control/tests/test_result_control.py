from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestResultControl(TransactionCase):
    """Test cases for result control workflow."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club_home = cls.env["federation.club"].create(
            {
                "name": "Home Club",
                "code": "HOME",
            }
        )
        cls.club_away = cls.env["federation.club"].create(
            {
                "name": "Away Club",
                "code": "AWAY",
            }
        )
        cls.team_home = cls.env["federation.team"].create(
            {
                "name": "Home Team",
                "club_id": cls.club_home.id,
            }
        )
        cls.team_away = cls.env["federation.team"].create(
            {
                "name": "Away Team",
                "club_id": cls.club_away.id,
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Test Season",
                "code": "TS2024",
                "date_start": "2024-09-01",
                "date_end": "2025-06-30",
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Result Rule Set",
                "code": "RRS",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Test Tournament",
                "season_id": cls.season.id,
                "date_start": "2024-09-01",
                "rule_set_id": cls.rule_set.id,
            }
        )
        cls.participant_home = cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_home.id,
            }
        )
        cls.participant_away = cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_away.id,
            }
        )
        Standing = cls.env.get("federation.standing")
        cls.standing = (
            Standing.create(
                {
                    "name": "Result Standing",
                    "tournament_id": cls.tournament.id,
                    "rule_set_id": cls.rule_set.id,
                }
            )
            if Standing
            else False
        )

        manager_group = cls.env.ref("sports_federation_base.group_federation_manager")
        validator_group = cls.env.ref(
            "sports_federation_result_control.group_result_validator"
        )
        approver_group = cls.env.ref(
            "sports_federation_result_control.group_result_approver"
        )
        cls.submitter_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Result Submitter",
                    "login": "result.submitter@example.com",
                    "email": "result.submitter@example.com",
                    "group_ids": [(6, 0, [manager_group.id])],
                }
            )
        )
        cls.verifier_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Result Verifier",
                    "login": "result.verifier@example.com",
                    "email": "result.verifier@example.com",
                    "group_ids": [(6, 0, [manager_group.id, validator_group.id])],
                }
            )
        )
        cls.approver_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Result Approver",
                    "login": "result.approver@example.com",
                    "email": "result.approver@example.com",
                    "group_ids": [(6, 0, [manager_group.id, approver_group.id])],
                }
            )
        )
        cls.match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team_home.id,
                "away_team_id": cls.team_away.id,
                "home_score": 2,
                "away_score": 1,
                "state": "done",
            }
        )

    def test_submit_result(self):
        """Test that submit result."""
        self.assertEqual(self.match.result_state, "draft")
        self.match.with_user(self.submitter_user).action_submit_result()
        self.assertEqual(self.match.result_state, "submitted")
        self.assertTrue(self.match.result_submitted_by_id)
        self.assertTrue(self.match.result_submitted_on)

    def test_verify_result(self):
        """Test that verify result."""
        self.match.with_user(self.submitter_user).action_submit_result()
        self.match.with_user(self.verifier_user).action_verify_result()
        self.assertEqual(self.match.result_state, "verified")
        self.assertTrue(self.match.result_verified_by_id)
        self.assertTrue(self.match.result_verified_on)

    def test_approve_result_sets_official_flag(self):
        """Test that approve result sets official flag."""
        self.match.with_user(self.submitter_user).action_submit_result()
        self.match.with_user(self.verifier_user).action_verify_result()
        self.assertFalse(self.match.include_in_official_standings)
        self.match.with_user(self.approver_user).action_approve_result()
        self.assertEqual(self.match.result_state, "approved")
        self.assertTrue(self.match.include_in_official_standings)
        self.assertTrue(self.match.result_approved_by_id)
        self.assertTrue(self.match.result_approved_on)
        if self.standing:
            self.assertEqual(self.standing.state, "computed")
            self.assertIn(self.match, self.standing._get_relevant_matches())

    def test_contest_requires_reason(self):
        """Test that contest requires reason."""
        self.match.with_user(self.submitter_user).action_submit_result()
        with self.assertRaises(ValidationError):
            self.match.action_contest_result()

    def test_contest_sets_flags(self):
        """Test that contest sets flags."""
        self.match.with_user(self.submitter_user).action_submit_result()
        self.match.with_user(self.verifier_user).action_verify_result()
        self.match.with_user(self.approver_user).action_approve_result()
        self.match.result_contest_reason = "Score disputed"
        self.match.action_contest_result()
        self.assertEqual(self.match.result_state, "contested")
        self.assertFalse(self.match.include_in_official_standings)
        if self.standing:
            self.assertNotIn(self.match, self.standing._get_relevant_matches())

    def test_correct_requires_reason(self):
        """Test that correct requires reason."""
        self.match.with_user(self.submitter_user).action_submit_result()
        self.match.result_contest_reason = "Score disputed"
        self.match.action_contest_result()
        with self.assertRaises(ValidationError):
            self.match.action_correct_result()

    def test_correct_sets_flags(self):
        """Test that correct sets flags."""
        self.match.with_user(self.submitter_user).action_submit_result()
        self.match.result_contest_reason = "Score disputed"
        self.match.action_contest_result()
        self.match.result_correction_reason = "Score updated"
        self.match.action_correct_result()
        self.assertEqual(self.match.result_state, "corrected")
        self.assertFalse(self.match.include_in_official_standings)

    def test_corrected_result_can_be_resubmitted(self):
        """Test that corrected result can be resubmitted."""
        self.match.with_user(self.submitter_user).action_submit_result()
        self.match.result_contest_reason = "Score disputed"
        self.match.action_contest_result()
        self.match.result_correction_reason = "Score corrected"
        self.match.action_correct_result()

        self.match.write({"home_score": 3, "away_score": 1})
        self.match.with_user(self.submitter_user).action_submit_result()
        self.assertEqual(self.match.result_state, "submitted")

    def test_reset_to_draft(self):
        """Test that reset to draft."""
        self.match.with_user(self.submitter_user).action_submit_result()
        self.match.with_user(self.verifier_user).action_verify_result()
        self.match.with_user(self.approver_user).action_approve_result()
        self.match.with_user(self.approver_user).action_reset_result_to_draft()
        self.assertEqual(self.match.result_state, "draft")
        self.assertFalse(self.match.include_in_official_standings)

    def test_invalid_transition_raises(self):
        """Test that invalid transition raises."""
        with self.assertRaises(ValidationError):
            self.match.action_verify_result()
        with self.assertRaises(ValidationError):
            self.match.action_approve_result()
        self.match.with_user(self.submitter_user).action_submit_result()
        with self.assertRaises(ValidationError):
            self.match.action_submit_result()

    def test_verify_requires_validator_role(self):
        """Test that verify requires validator role."""
        self.match.with_user(self.submitter_user).action_submit_result()
        with self.assertRaises(ValidationError):
            self.match.with_user(self.submitter_user).action_verify_result()

    def test_approve_requires_approver_role(self):
        """Test that approve requires approver role."""
        self.match.with_user(self.submitter_user).action_submit_result()
        self.match.with_user(self.verifier_user).action_verify_result()
        with self.assertRaises(ValidationError):
            self.match.with_user(self.verifier_user).action_approve_result()

    def test_same_user_cannot_verify_own_submission(self):
        """Test that same user cannot verify own submission."""
        self.match.with_user(self.verifier_user).action_submit_result()
        with self.assertRaises(ValidationError):
            self.match.with_user(self.verifier_user).action_verify_result()

    def test_same_user_cannot_approve_own_verification(self):
        """Test that same user cannot approve own verification."""
        self.match.with_user(self.submitter_user).action_submit_result()
        self.match.with_user(self.approver_user).action_verify_result()
        with self.assertRaises(ValidationError):
            self.match.with_user(self.approver_user).action_approve_result()

    def test_approved_scores_are_immutable(self):
        """Test that approved scores are immutable."""
        self.match.with_user(self.submitter_user).action_submit_result()
        self.match.with_user(self.verifier_user).action_verify_result()
        self.match.with_user(self.approver_user).action_approve_result()
        with self.assertRaises(ValidationError):
            self.match.write({"home_score": 5})

    def test_result_audit_entries_follow_workflow_transitions(self):
        """Test that result audit entries follow workflow transitions."""
        self.match.with_user(self.submitter_user).action_submit_result()
        self.match.with_user(self.verifier_user).action_verify_result()
        self.match.with_user(self.approver_user).action_approve_result()

        event_types = self.match.result_audit_ids.mapped("event_type")
        self.assertIn("submitted", event_types)
        self.assertIn("verified", event_types)
        self.assertIn("approved", event_types)

    def test_contest_and_correction_reasons_are_audited(self):
        """Test that contest and correction reasons are audited."""
        self.match.with_user(self.submitter_user).action_submit_result()
        self.match.result_contest_reason = "Score disputed"
        self.match.action_contest_result()
        self.match.result_correction_reason = "Score corrected after review"
        self.match.action_correct_result()

        contest_entry = self.match.result_audit_ids.filtered(
            lambda entry: entry.event_type == "contested"
        )[:1]
        correction_entry = self.match.result_audit_ids.filtered(
            lambda entry: entry.event_type == "corrected"
        )[:1]

        self.assertTrue(contest_entry)
        self.assertEqual(contest_entry.reason, "Score disputed")
        self.assertTrue(correction_entry)
        self.assertEqual(correction_entry.reason, "Score corrected after review")
