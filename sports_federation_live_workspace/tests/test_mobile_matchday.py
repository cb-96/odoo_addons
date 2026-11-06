from unittest.mock import patch
from uuid import uuid4
from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, HttpCase, tagged
from .test_commands import LiveFixture


@tagged("post_install", "-at_install", "sf_mobile_matchday")
class TestMobileMatchday(LiveFixture, TransactionCase):
    def setUp(self):
        super().setUp()
        clock = patch(
            "odoo.fields.Datetime.now",
            return_value=fields.Datetime.to_datetime("2026-06-15 17:00:00"),
        )
        clock.start()
        self.addCleanup(clock.stop)
        self.commands = self.env["federation.court.commands"].with_user(self.operator)

    def _open(self):
        return self.commands.open_match(
            self.matchday.id, self.slot.court_id.id, self.match.id
        )

    def _command(self, opened, operation="save"):
        return {
            "key": str(uuid4()),
            "revision": opened["revision"],
            "signature": opened["signature"],
            "operation": operation,
            "payload": {**opened["payload"], "home": 2, "away": 1},
        }

    def _sync(self, commands):
        return self.commands.sync(
            self.matchday.id, self.slot.court_id.id, self.match.id, commands
        )

    def test_inspect_returns_current_status(self):
        opened = self._open()
        inspected = self.commands.inspect(
            self.matchday.id, self.slot.court_id.id, self.match.id
        )
        self.assertEqual(inspected["revision"], opened["revision"])
        self.assertEqual(inspected["result_state"], self.match.result_state)

    def test_acknowledgement_contains_original_keys(self):
        command = self._command(self._open())
        self.assertEqual(self._sync([command])["acknowledged_keys"], [command["key"]])

    def test_lost_save_response_replay_has_one_receipt(self):
        command = self._command(self._open())
        first = self._sync([command])
        replay = self._sync([command])
        self.assertEqual(first["acknowledged_keys"], replay["acknowledged_keys"])
        self.assertEqual(first["current"]["revision"], replay["current"]["revision"])
        self.assertEqual(
            self.env["federation.court.receipt"]
            .sudo()
            .search_count([("key", "=", command["key"])]),
            1,
        )

    def test_lost_submission_response_does_not_resubmit(self):
        command = self._command(self._open(), "submit")
        first = self._sync([command])
        replay = self._sync([command])
        self.assertTrue(replay["current"]["submitted"])
        self.assertEqual(first["current"]["revision"], replay["current"]["revision"])
        self.assertEqual(
            self.env["federation.court.receipt"]
            .sudo()
            .search_count([("key", "=", command["key"])]),
            1,
        )

    def test_other_session_revision_rejects_stale_command(self):
        opened = self._open()
        self._sync([self._command(opened)])
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._sync([self._command(opened)])

    def test_revoked_court_access_rejects_inspection(self):
        self._open()
        self.access.active = False
        with self.assertRaises(AccessError):
            self.commands.inspect(
                self.matchday.id, self.slot.court_id.id, self.match.id
            )

    def test_closed_session_rejects_sync(self):
        command = self._command(self._open())
        self.matchday_session.write({"state": "closed"})
        with self.assertRaises(ValidationError):
            self._sync([command])

    def test_inspection_does_not_submit(self):
        self._open()
        self.commands.inspect(self.matchday.id, self.slot.court_id.id, self.match.id)
        self.assertEqual(self.match.result_state, "draft")

    def test_device_checkin_request_is_not_attendance(self):
        assignment = self.assignment.with_user(self.official_user)
        assignment._portal_action_confirm(user=self.official_user)
        assignment._request_mobile_checkin(
            self.official_user, assignment._coverage_signature()
        )
        self.assertTrue(assignment.checkin_requested_on)
        self.assertFalse(assignment.present_on)

    def test_checkin_request_replay_is_idempotent(self):
        assignment = self.assignment.with_user(self.official_user)
        assignment._portal_action_confirm(user=self.official_user)
        signature = assignment._coverage_signature()
        assignment._request_mobile_checkin(self.official_user, signature)
        timestamp = assignment.checkin_requested_on
        assignment._request_mobile_checkin(self.official_user, signature)
        self.assertEqual(assignment.checkin_requested_on, timestamp)

    def test_other_official_cannot_checkin(self):
        with self.assertRaises(AccessError):
            self.assignment.with_user(
                self.other_referee.user_id
            )._request_mobile_checkin(
                self.other_referee.user_id, self.assignment._coverage_signature()
            )

    def test_stale_checkin_signature_rejected(self):
        assignment = self.assignment.with_user(self.official_user)
        assignment._portal_action_confirm(user=self.official_user)
        with self.assertRaises(ValidationError):
            assignment._request_mobile_checkin(self.official_user, "stale")

    def test_unaccepted_checkin_rejected(self):
        assignment = self.assignment.with_user(self.official_user)
        with self.assertRaises(ValidationError):
            assignment._request_mobile_checkin(
                self.official_user, assignment._coverage_signature()
            )

    def test_checkin_fields_cannot_be_forged(self):
        with self.assertRaises(AccessError):
            self.assignment.write({"checkin_requested_on": fields.Datetime.now()})

    def test_organiser_confirms_attendance_separately(self):
        assignment = self.assignment.with_user(self.official_user)
        assignment._portal_action_confirm(user=self.official_user)
        assignment._request_mobile_checkin(
            self.official_user, assignment._coverage_signature()
        )
        self.assignment.action_mark_present()
        self.assertTrue(self.assignment.coverage_present)

    def test_replacement_retains_old_assignment_and_requires_acceptance(self):
        wizard = self.env["federation.coverage.resolve.wizard"].create(
            {
                "match_id": self.match.id,
                "operation": "replace",
                "assignment_id": self.assignment.id,
                "selected_role": self.assignment.role,
                "referee_id": self.other_referee.id,
                "reason": "Original official unavailable",
            }
        )
        wizard.expected_signature = wizard._signature()
        wizard.action_apply()
        replacement = wizard.result_assignment_id
        self.assertEqual(self.assignment.state, "cancelled")
        self.assertEqual(replacement.replaces_id, self.assignment)
        self.assertFalse(replacement.coverage_accepted)
        wizard.action_apply()
        self.assertEqual(len(self.assignment.replacement_ids), 1)


@tagged("post_install", "-at_install", "sf_mobile_matchday")
class TestMobileHttp(LiveFixture, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator.password = "mobile-test-password"
        cls.official_user.password = "mobile-test-password"

    def test_mobile_home_for_official(self):
        self.authenticate(self.official_user.login, "mobile-test-password")
        response = self.url_open("/my/matchday-mobile")
        self.assertEqual(response.status_code, 200)
        self.assertIn("My official assignments", response.text)
        self.assertNotIn("Organiser coverage and attendance", response.text)

    def test_mobile_home_for_court_operator(self):
        self.authenticate(self.operator.login, "mobile-test-password")
        response = self.url_open("/my/matchday-mobile")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Run my court", response.text)

    def test_official_detail_has_venue(self):
        self.authenticate(self.official_user.login, "mobile-test-password")
        response = self.url_open("/my/duty-assignments/%s" % self.assignment.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Venue and check-in", response.text)

    def test_checkin_post_requires_csrf(self):
        self.authenticate(self.official_user.login, "mobile-test-password")
        response = self.url_open(
            "/my/duty-assignments/%s/checkin" % self.assignment.id,
            data={},
            method="POST",
        )
        self.assertEqual(response.status_code, 400)

    def test_non_manager_cannot_open_replacement(self):
        self.authenticate(self.official_user.login, "mobile-test-password")
        response = self.url_open(
            "/my/matchday-mobile/assignments/%s/replace" % self.assignment.id
        )
        self.assertEqual(response.status_code, 404)
