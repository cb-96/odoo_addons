"""Twenty-one ORM contracts for schedule-linked duty coverage.

These tests exercise persisted models, not mocked readiness calculations.
They do not replace independent-transaction concurrency or HTTP/CSRF tests.
"""
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from .common import CoverageFixture


@tagged("post_install", "-at_install", "sf_release_confidence", "sf_duty_coverage")
class TestCoverage(CoverageFixture, TransactionCase):
    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.to_datetime("2026-06-15 17:00:00")
        clock = patch("odoo.fields.Datetime.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def _snapshot(self, match=None):
        self.env.flush_all()
        self.env.invalidate_all()
        return (match or self.match)._coverage_snapshot()

    def _wizard(self, **values):
        wizard = self.env["federation.coverage.resolve.wizard"].create(
            {"match_id": self.match.id, **values}
        )
        # Capture the same preview signature as the UI, without changing policy.
        wizard.expected_signature = wizard._signature()
        return wizard

    def _accept(self, assignment=None):
        assignment = assignment or self.assignment
        assignment._portal_action_confirm(user=assignment.referee_id.user_id)
        assignment.invalidate_recordset()
        return assignment

    def _assert_rejected(self, error, callback):
        # Roll back any partial mutation before assertRaises consumes the error.
        with self.assertRaises(error), self.env.cr.savepoint():
            callback()
        self.env.invalidate_all()

    def _assignments(self):
        return self.env["federation.match.referee"].search(
            [("match_id", "=", self.match.id)], order="id"
        )

    def _activities(self):
        activity_type = self.env.ref(
            "sports_federation_duty_coverage.coverage_activity_type"
        )
        return self.env["mail.activity"].search(
            [
                ("res_model", "=", "federation.match"),
                ("res_id", "=", self.match.id),
                ("activity_type_id", "=", activity_type.id),
            ]
        )

    def test_zero_assignments_uncovered(self):
        """Cancelling the last assignment exposes the required unfilled slot."""
        self.assignment.action_cancel()
        snapshot = self._snapshot()
        self.assertEqual(snapshot["state"], "uncovered")
        self.assertEqual(snapshot["required"], 1)
        self.assertEqual(snapshot["assigned"], 0)
        self.assertEqual(snapshot["missing"]["head"], 1)
        self.assertTrue(self.assignment.exists(), "Cancellation must retain history")

    def test_assignment_not_acceptance(self):
        """A draft assignment is neither acknowledgement nor attendance."""
        snapshot = self._snapshot()
        self.assertEqual(snapshot["state"], "needs_action")
        self.assertEqual(snapshot["assigned"], 1)
        self.assertEqual(snapshot["accepted"], 0)
        self.assertEqual(snapshot["present"], 0)
        self.assertEqual(snapshot["completed"], 0)
        self.assertFalse(self.assignment.accepted_on)
        self.assertFalse(self.assignment.coverage_accepted)

    def test_no_requirement_distinct_from_unchecked(self):
        """Explicit zero requirements differ from absent requirements."""
        self.assignment.action_cancel()
        self.match.write({"coverage_override": True, "coverage_head_required": 0})
        self.assertEqual(self._snapshot()["state"], "not_required")
        self.assertEqual(self._snapshot()["required"], 0)
        self.assertFalse(self.match._get_effective_officiating_rule_set())
        self.match.coverage_override = False
        self.assertEqual(self._snapshot()["state"], "unchecked")

    def test_individual_acceptance_and_attendance(self):
        """Completion requires distinct individual and manager evidence."""
        self._accept()
        self.assertEqual(self._snapshot()["state"], "ready")
        self.assertEqual(self.assignment.accepted_by_id, self.official_user)
        self.assertEqual(self.assignment.accepted_on, self.now)
        self.assertFalse(self.assignment.present_on)
        self._assert_rejected(ValidationError, self.assignment.action_done)
        self.assignment.with_user(self.manager).action_mark_present()
        self.assertEqual(self.assignment.present_by_id, self.manager)
        self.assertEqual(self.assignment.present_on, self.now)
        self.assignment.with_user(self.manager).action_done()
        self.assertEqual(self.assignment.state, "done")
        self.assertEqual(self.assignment.completed_on, self.now)
        self.assertEqual(self._snapshot()["completed"], 1)
        self.assignment.with_user(self.manager).action_done()
        self.assertEqual(self._snapshot()["completed"], 1)

    def test_duplicate_acceptance_idempotent(self):
        """Retrying acknowledgement does not replace its original evidence."""
        self._accept()
        evidence = self.assignment.read(
            ["accepted_on", "accepted_by_id", "accepted_signature"]
        )[0]
        with patch(
            "odoo.fields.Datetime.now",
            return_value=fields.Datetime.to_datetime("2026-06-15 17:05:00"),
        ):
            self._accept()
        self.assertEqual(
            self.assignment.read(
                ["accepted_on", "accepted_by_id", "accepted_signature"]
            )[0],
            evidence,
        )
        self.assertEqual(self._snapshot()["accepted"], 1)

    def test_manager_cannot_impersonate_acceptance(self):
        """Coordinator privileges do not grant individual acknowledgement."""
        self._assert_rejected(
            AccessError, self.assignment.with_user(self.manager).action_confirm
        )
        self.assertEqual(self.assignment.state, "draft")
        self.assertFalse(self.assignment.accepted_on)

    def test_other_official_cannot_accept(self):
        """A foreign login cannot acknowledge an owned assignment."""
        self._assert_rejected(
            AccessError,
            lambda: self.assignment._portal_action_confirm(user=self.other_user),
        )
        self.assertFalse(self.assignment.accepted_on)
        self.assertEqual(self.assignment.state, "draft")

    def test_portal_cannot_mark_present_even_elevated(self):
        """Elevation alone must not turn a portal actor into a manager."""
        self._accept()
        self._assert_rejected(
            AccessError,
            self.assignment.with_user(self.official_user).sudo().action_mark_present,
        )
        self.assertFalse(self.assignment.present_on)
        self.assertFalse(self.assignment.present_by_id)
        self.assertTrue(self.assignment.coverage_accepted)

    def test_raw_evidence_write_rejected(self):
        """Evidence fields cannot be fabricated through ordinary ORM writes."""
        for values in (
            {"accepted_on": self.now},
            {"accepted_signature": "fabricated"},
            {"present_on": self.now},
            {"replaces_id": self.other_assignment.id},
        ):
            with self.subTest(values=values):
                self._assert_rejected(
                    ValidationError, lambda values=values: self.assignment.write(values)
                )
        self.assertFalse(self.assignment.accepted_on)
        self.assertFalse(self.assignment.present_on)
        self.assertFalse(self.assignment.replaces_id)

    def test_availability_not_checked(self):
        """Missing availability is not silently interpreted as available."""
        self.referee.availability_ids.write({"active": False})
        self._assert_rejected(ValidationError, self._accept)
        self.assertFalse(self.assignment.coverage_eligible)
        self.assertFalse(self.assignment.accepted_on)
        self.assertEqual(self._snapshot()["state"], "needs_action")

    def test_expired_certification(self):
        """An expired certificate cannot be bypassed by the legacy level."""
        self.env["federation.referee.certification"].create(
            {
                "name": "Expired coverage certificate",
                "referee_id": self.referee.id,
                "level": "national",
                "issue_date": "2025-01-01",
                "expiry_date": "2025-12-31",
            }
        )
        self.assertTrue(self.referee.certification_level)
        self._assert_rejected(ValidationError, self._accept)
        self.assertFalse(self.assignment.coverage_eligible)
        self.assertFalse(self.assignment.accepted_on)

    def test_playing_conflict_visible(self):
        """An explicitly linked player cannot officiate their playing team."""
        player = self.env["federation.player"].create(
            {
                "first_name": "Coverage",
                "last_name": "Player",
                "club_id": self.club.id,
                "team_ids": [(6, 0, [self.home_team.id])],
            }
        )
        self.referee.coverage_player_id = player
        self._snapshot()
        self.assertFalse(self.assignment.coverage_eligible)
        self.assertTrue(self.assignment.coverage_feedback)
        self._assert_rejected(ValidationError, self._accept)
        self.assertFalse(self.assignment.accepted_on)

    def test_officiating_overlap_visible(self):
        """A second overlapping duty invalidates current eligibility."""
        self.other_match.date_scheduled = self.slot.start_datetime
        overlapping = self.env["federation.match.referee"].create(
            {
                "match_id": self.other_match.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        self.assertIn(overlapping, self.assignment._get_overlapping_assignments())
        self._assert_rejected(ValidationError, self._accept)
        self.assertFalse(self.assignment.coverage_eligible)
        self.assertEqual(self._snapshot()["state"], "needs_action")

    def test_schedule_change_invalidates_acceptance(self):
        """A changed assignment signature makes acknowledgement stale."""
        self._accept()
        original_signature = self.assignment.accepted_signature
        original_timestamp = self.assignment.accepted_on
        self.match.date_scheduled = "2026-06-15 19:00:00"
        snapshot = self._snapshot()
        self.assertNotEqual(
            original_signature, self.assignment._coverage_signature()
        )
        self.assertFalse(self.assignment.coverage_accepted)
        self.assertEqual(self.assignment.accepted_on, original_timestamp)
        self.assertEqual(snapshot["accepted"], 0)
        self.assertEqual(snapshot["state"], "needs_action")
        self._accept()
        self.assertTrue(self.assignment.coverage_accepted)
        self.assertEqual(
            self.assignment.accepted_signature, self.assignment._coverage_signature()
        )

    def test_stale_preview_rejected(self):
        """A resolution cannot apply after its previewed match changes."""
        wizard = self._wizard(
            operation="replace", assignment_id=self.assignment.id,
            referee_id=self.other_referee.id, reason="Unavailable",
        )
        before_ids = self._assignments().ids
        self.match.date_scheduled = "2026-06-15 19:00:00"
        self._assert_rejected(ValidationError, wizard.action_apply)
        self.assertEqual(self._assignments().ids, before_ids)
        self.assertEqual(self.assignment.state, "draft")
        self.assertFalse(wizard.applied)
        self.assertFalse(self.assignment.replacement_ids)

    def test_replacement_preserves_other_assignments_and_history(self):
        """Replacement retains the accepted predecessor and unrelated duties."""
        self._accept()
        original_acceptance = self.assignment.accepted_on
        unrelated = self.other_assignment.read(["state", "referee_id", "role"])[0]
        wizard = self._wizard(
            operation="replace", assignment_id=self.assignment.id,
            referee_id=self.other_referee.id, reason="Unavailable",
        )
        action = wizard.action_apply()
        successor = wizard.result_assignment_id
        self.assertTrue(successor)
        self.assertEqual(action["res_id"], self.match.id)
        self.assertEqual(self.assignment.state, "cancelled")
        self.assertEqual(self.assignment.accepted_on, original_acceptance)
        self.assertEqual(successor.replaces_id, self.assignment)
        self.assertEqual(successor.replacement_reason, "Unavailable")
        self.assertEqual(successor.role, self.assignment.role)
        self.assertEqual(successor.state, "draft")
        self.assertFalse(successor.accepted_on)
        self.assertFalse(successor.present_on)
        self.assertEqual(
            self.other_assignment.read(["state", "referee_id", "role"])[0], unrelated
        )
        before_ids = self._assignments().ids
        wizard.action_apply()
        self.assertEqual(self._assignments().ids, before_ids)
        self.assertEqual(self.assignment.replacement_ids, successor)

    def test_failed_replacement_rolls_back(self):
        """A failure after cancellation and successor creation rolls back both."""
        wizard = self._wizard(
            operation="replace", assignment_id=self.assignment.id,
            referee_id=self.other_referee.id, reason="Unavailable",
        )
        before_ids = self._assignments().ids
        match_class = type(self.env["federation.match"])
        original_sync = match_class._coverage_sync_escalations
        observed = []

        def fail_after_apply(records):
            if wizard.applied:
                # Prove we reached the post-mutation hook before injecting failure.
                observed.append((
                    self.assignment.state,
                    wizard.result_assignment_id.replaces_id.id,
                ))
                raise ValidationError("Injected post-mutation failure")
            return original_sync(records)

        with patch.object(
            match_class, "_coverage_sync_escalations", autospec=True,
            side_effect=fail_after_apply,
        ):
            self._assert_rejected(ValidationError, wizard.action_apply)
        self.assertEqual(observed, [("cancelled", self.assignment.id)])
        self.assertEqual(self._assignments().ids, before_ids)
        self.assertEqual(self.assignment.state, "draft")
        self.assertFalse(self.assignment.cancelled_on)
        self.assertFalse(self.assignment.replacement_ids)
        self.assertFalse(wizard.applied)
        self.assertFalse(wizard.result_assignment_id)

    def test_club_nomination_not_individual_acceptance(self):
        """Coordinator linkage creates one draft, explicitly identified duty."""
        player = self.env["federation.player"].create(
            {"first_name": "Club", "last_name": "Official", "club_id": self.club.id}
        )
        self.other_referee.coverage_player_id = player
        duty = self.env["federation.match.club.referee.duty"].create(
            {"match_id": self.match.id, "club_id": self.club.id, "role": "table"}
        )
        duty.action_open()
        duty.action_nominate(player.id)
        self.assertEqual(duty.state, "nominated")
        duty.action_confirm()
        assignment = duty.assignment_id
        self.assertEqual(duty.state, "confirmed")
        self.assertEqual(assignment.referee_id, self.other_referee)
        self.assertEqual(assignment.state, "draft")
        self.assertFalse(assignment.accepted_on)
        self.assertFalse(assignment.coverage_accepted)
        before_ids = self._assignments().ids
        duty.action_confirm()
        self.assertEqual(duty.assignment_id, assignment)
        self.assertEqual(self._assignments().ids, before_ids)
        self.assertNotEqual(self._snapshot()["state"], "ready")

    def test_escalation_idempotent_and_cleanup(self):
        """One overdue activity is removed on readiness and presence recovery."""
        self.match._coverage_sync_escalations()
        activities = self._activities()
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities.user_id, self.manager)
        self.match._coverage_sync_escalations()
        self.assertEqual(self._activities(), activities)
        self._accept()
        self.assertFalse(self._activities())
        with patch(
            "odoo.fields.Datetime.now",
            return_value=fields.Datetime.to_datetime("2026-06-15 18:00:00"),
        ):
            self.match._coverage_sync_escalations()
            self.assertEqual(len(self._activities()), 1)
            self.match._coverage_sync_escalations()
            self.assertEqual(len(self._activities()), 1)
            self.assignment.with_user(self.manager).action_mark_present()
            self.assertFalse(self._activities())

    def test_cross_match_resolution_rejected(self):
        """An assignment ID from another match cannot be replaced here."""
        wizard = self._wizard(
            operation="replace", assignment_id=self.other_assignment.id,
            referee_id=self.referee.id, reason="Wrong match",
        )
        before_ids = self._assignments().ids
        self._assert_rejected(ValidationError, wizard.action_apply)
        self.assertEqual(self._assignments().ids, before_ids)
        self.assertEqual(self.other_assignment.state, "draft")
        self.assertFalse(self.other_assignment.replacement_ids)
        self.assertFalse(wizard.applied)

    def test_delete_history_rejected(self):
        """Cancellation does not permit deletion of assignment history."""
        self.assignment.action_cancel()
        self._assert_rejected(ValidationError, self.assignment.unlink)
        self.assertTrue(self.assignment.exists())
        self.assertEqual(self.assignment.state, "cancelled")
