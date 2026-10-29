from unittest.mock import patch
from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from .common import CoverageFixture


@tagged("post_install", "-at_install", "sf_release_confidence", "sf_duty_coverage")
class TestCoverage(CoverageFixture, TransactionCase):
    def _wizard(self, **values):
        w = self.env["federation.coverage.resolve.wizard"].create(
            {"match_id": self.match.id, **values}
        )
        w.expected_signature = w._signature()
        return w

    def _accept(self, a=None):
        a = a or self.assignment
        a._portal_action_confirm(user=a.referee_id.user_id)
        a.invalidate_recordset()

    def test_zero_assignments_uncovered(self):
        self.assignment.action_cancel()
        self.assertEqual(self.match._coverage_snapshot()["state"], "uncovered")

    def test_assignment_not_acceptance(self):
        self.assertEqual(self.match._coverage_snapshot()["state"], "needs_action")
        self.assertFalse(self.assignment.coverage_accepted)

    def test_no_requirement_distinct_from_unchecked(self):
        self.assignment.action_cancel()
        self.match.coverage_head_required = 0
        self.assertEqual(self.match._coverage_snapshot()["state"], "not_required")
        self.match.coverage_override = False
        self.assertEqual(self.match._coverage_snapshot()["state"], "unchecked")

    def test_individual_acceptance_and_attendance(self):
        self._accept()
        self.assertEqual(self.match._coverage_snapshot()["state"], "ready")
        self.assertFalse(self.assignment.coverage_present)
        with self.assertRaises(ValidationError):
            self.assignment.action_done()
        self.assignment.action_mark_present()
        self.assignment.action_done()
        self.assertEqual(self.assignment.state, "done")
        self.assertEqual(self.match._coverage_snapshot()["completed"], 1)

    def test_duplicate_acceptance_idempotent(self):
        self._accept()
        stamp = self.assignment.accepted_on
        self._accept()
        self.assertEqual(self.assignment.accepted_on, stamp)

    def test_manager_cannot_impersonate_acceptance(self):
        with self.assertRaises(AccessError):
            self.assignment.with_user(self.manager).action_confirm()

    def test_other_official_cannot_accept(self):
        with self.assertRaises(AccessError):
            self.assignment._portal_action_confirm(user=self.other_user)

    def test_portal_cannot_mark_present_even_elevated(self):
        with self.assertRaises(AccessError):
            self.assignment.with_user(self.official_user).sudo().action_mark_present()

    def test_raw_evidence_write_rejected(self):
        with self.assertRaises(ValidationError):
            self.assignment.write({"accepted_on": fields.Datetime.now()})

    def test_availability_not_checked(self):
        self.referee.availability_ids.active = False
        self.assertIn("Availability is not checked", self.assignment.coverage_feedback)
        with self.assertRaises(ValidationError):
            self._accept()

    def test_expired_certification(self):
        self.env["federation.referee.certification"].create(
            {
                "name": "Expired coverage certificate",
                "referee_id": self.referee.id,
                "level": "national",
                "issue_date": "2025-01-01",
                "expiry_date": "2025-12-31",
            }
        )
        with self.assertRaises(ValidationError):
            self._accept()

    def test_playing_conflict_visible(self):
        player = self.env["federation.player"].create(
            {
                "name": "Coverage player",
                "first_name": "Coverage",
                "last_name": "Player",
                "club_id": self.club.id,
                "team_ids": [(6, 0, [self.home_team.id])],
            }
        )
        self.referee.coverage_player_id = player
        self.assertIn("team playing", self.assignment.coverage_feedback)

    def test_officiating_overlap_visible(self):
        self.other_match.date_scheduled = self.match.date_scheduled
        self.env["federation.match.referee"].create(
            {
                "match_id": self.other_match.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        self.assertIn(
            "officiating assignment overlaps", self.assignment.coverage_feedback
        )

    def test_schedule_change_invalidates_acceptance(self):
        self._accept()
        self.match.date_scheduled = "2026-06-15 19:00:00"
        self.assignment.invalidate_recordset()
        self.assertFalse(self.assignment.coverage_accepted)
        self.assertEqual(self.match._coverage_snapshot()["state"], "needs_action")

    def test_stale_preview_rejected(self):
        w = self._wizard(
            operation="replace",
            assignment_id=self.assignment.id,
            referee_id=self.other_referee.id,
            reason="Unavailable",
        )
        self.match.date_scheduled = "2026-06-15 19:00:00"
        with self.assertRaises(ValidationError):
            w.action_apply()
        self.assertEqual(self.assignment.state, "draft")

    def test_replacement_preserves_other_assignments_and_history(self):
        w = self._wizard(
            operation="replace",
            assignment_id=self.assignment.id,
            referee_id=self.other_referee.id,
            reason="Unavailable",
        )
        w.action_apply()
        new = w.result_assignment_id
        self.assertEqual(self.assignment.state, "cancelled")
        self.assertEqual(new.replaces_id, self.assignment)
        self.assertEqual(self.other_assignment.state, "draft")
        self.assertFalse(new.coverage_accepted)
        w.action_apply()
        self.assertEqual(len(self.assignment.replacement_ids), 1)

    def test_failed_replacement_rolls_back(self):
        w = self._wizard(
            operation="replace",
            assignment_id=self.assignment.id,
            referee_id=self.other_referee.id,
            reason="Unavailable",
        )
        self.other_referee.active = False
        with self.assertRaises(ValidationError):
            w.action_apply()
        self.assertEqual(self.assignment.state, "draft")
        self.assertFalse(self.assignment.replacement_ids)

    def test_club_nomination_not_individual_acceptance(self):
        player = self.env["federation.player"].create(
            {
                "name": "Club official",
                "first_name": "Club",
                "last_name": "Official",
                "club_id": self.club.id,
            }
        )
        self.other_referee.coverage_player_id = player
        duty = self.env["federation.match.club.referee.duty"].create(
            {"match_id": self.match.id, "club_id": self.club.id, "role": "table"}
        )
        duty.action_open()
        duty.action_nominate(player.id)
        duty.action_confirm()
        self.assertEqual(duty.assignment_id.state, "draft")
        self.assertFalse(duty.assignment_id.coverage_accepted)
        count = len(self.match.referee_assignment_ids)
        duty.action_confirm()
        self.assertEqual(len(self.match.referee_assignment_ids), count)

    def test_escalation_idempotent_and_cleanup(self):
        self.match._coverage_sync_escalations()
        typ = self.env.ref("sports_federation_duty_coverage.coverage_activity_type")

        def count():
            return len(
                self.match.activity_ids.filtered(lambda a: a.activity_type_id == typ)
            )

        self.assertEqual(count(), 1)
        self.match._coverage_sync_escalations()
        self.assertEqual(count(), 1)
        with patch(
            "odoo.fields.Datetime.now",
            return_value=fields.Datetime.to_datetime("2026-06-15 17:00:00"),
        ):
            self._accept()
        self.assertEqual(count(), 0)

    def test_cross_match_resolution_rejected(self):
        w = self._wizard(
            operation="replace",
            assignment_id=self.other_assignment.id,
            referee_id=self.referee.id,
            reason="Wrong match",
        )
        with self.assertRaises(ValidationError):
            w.action_apply()

    def test_delete_history_rejected(self):
        with self.assertRaises(ValidationError):
            self.assignment.unlink()
