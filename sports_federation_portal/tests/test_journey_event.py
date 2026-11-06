from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_journey_instrumentation")
class TestJourneyEvent(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Event = cls.env["federation.journey.event"]
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create({"name": "Journey User", "login": "journey.user@example.test"})
        )

    def test_unknown_events_are_not_recorded(self):
        self.assertFalse(self.Event.record("j.unknown", "banana"))

    def test_anonymous_visitors_are_never_recorded(self):
        public = self.env.ref("base.public_user")
        self.assertFalse(
            self.Event.with_user(public).record("j.public", "entry", session="s")
        )
        self.assertFalse(self.Event.search([("journey", "=", "j.public")]))

    def test_the_raw_session_is_never_stored(self):
        event_id = self.Event.with_user(self.user).record(
            "j.session", "entry", session="raw-sid-123"
        )
        event = self.Event.browse(event_id)
        self.assertTrue(event.session_key)
        self.assertNotIn("raw-sid-123", event.session_key)

    def test_repeated_entries_inside_the_window_are_recorded_once(self):
        user_events = self.Event.with_user(self.user)
        first = user_events.record("j.dedupe", "entry", session="s", dedupe_seconds=60)
        second = user_events.record("j.dedupe", "entry", session="s", dedupe_seconds=60)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(self.Event.search_count([("journey", "=", "j.dedupe")]), 1)

    def test_repeating_a_failed_command_is_a_retry(self):
        user_events = self.Event.with_user(self.user)
        self.assertFalse(user_events.record_attempt("j.retry"))
        user_events.record("j.retry", "validation_error")
        self.assertTrue(user_events.record_attempt("j.retry"))
        self.assertEqual(
            self.Event.search_count(
                [("journey", "=", "j.retry"), ("event", "=", "retry")]
            ),
            1,
        )
        self.assertFalse(user_events.record_attempt("j.other"))

    def test_recording_never_raises(self):
        with patch.object(type(self.Event), "create", side_effect=RuntimeError("boom")):
            self.assertFalse(self.Event.with_user(self.user).record("j.boom", "entry"))

    def test_report_summarises_events_and_task_closure(self):
        user_events = self.Event.with_user(self.user)
        user_events.record("j.report", "entry", screen="home", session="rep-1")
        user_events.record("j.report.cmd", "action", session="rep-1")
        user_events.record("j.report.cmd", "validation_error", session="rep-1")
        report = self.Event.report(days=1)
        self.assertEqual(report["by_journey"]["j.report"]["entries"], 1)
        self.assertEqual(
            report["by_journey"]["j.report.cmd"]["validation_error_rate"], 0.5
        )
        task_types = set(
            dict(
                self.env["federation.operation.task"]
                ._fields["task_type"]
                ._description_selection(self.env)
            )
        )
        self.assertEqual(set(report["task_closure"]), task_types)

    def test_old_events_are_pruned_and_recent_ones_kept(self):
        old = self.Event.sudo().create(
            {
                "journey": "j.old",
                "event": "entry",
                "occurred_on": fields.Datetime.now() - timedelta(days=400),
            }
        )
        recent = self.Event.sudo().create({"journey": "j.recent", "event": "entry"})
        self.Event._cron_prune(batch=100000)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())

    def test_events_are_read_only_for_managers(self):
        manager = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Journey Manager",
                    "login": "journey.manager@example.test",
                    "group_ids": [
                        (
                            6,
                            0,
                            [
                                self.env.ref(
                                    "sports_federation_base.group_federation_manager"
                                ).id
                            ],
                        )
                    ],
                }
            )
        )
        events = self.Event.with_user(manager)
        events.check_access("read")
        with self.assertRaises(Exception):
            events.check_access("create")
