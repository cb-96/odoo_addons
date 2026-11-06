"""Execute production queue methods with isolated doubles; no SMTP or Odoo."""
from contextlib import nullcontext
from datetime import datetime, timedelta
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest

from ci.check_notification_side_effect_contract import violations
from ci.production_method import load_method

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "sports_federation_notifications/models"
NOW = datetime(2026, 11, 6, 12)


def feedback(error):
    text = str(error)
    return ("retryable_delivery" if "timeout" in text else "configuration_error", text)


def method(filename, name):
    scope = {
        "_": lambda text: text, "ValidationError": ValueError,
        "DeadlockDetected": type("DeadlockDetected", (Exception,), {}),
        "SerializationFailure": type("SerializationFailure", (Exception,), {}),
        "fields": SimpleNamespace(Datetime=SimpleNamespace(now=lambda: NOW)),
        "timedelta": timedelta, "MAX_AUTOMATIC_ATTEMPTS": 3,
        "build_failure_feedback": feedback, "_logger": logging.getLogger("outbox_test"),
    }
    return load_method("sports_federation_notifications/models/" + filename, name, scope)


class Mail:
    def __init__(self, state="outgoing", present=True):
        self.id = 7
        self.state = state
        self.failure_reason = "SMTP timeout"
        self.present = present
        self.writes = []

    def __bool__(self):
        return self.present

    def exists(self):
        return self

    def invalidate_recordset(self, names):
        pass

    def write(self, values):
        self.writes.append(values)
        self.__dict__.update(values)


class Log:
    def __init__(self, mail=None):
        self.id = 1
        self.mail_id = mail or Mail(present=False)
        self.state = "pending"
        self.queued_on = NOW
        self.sent_on = False
        self.attempt_count = 1
        self.next_attempt_on = False
        self.notification_type = "email"
        self.writes = []

    def ensure_one(self):
        pass

    def write(self, values):
        self.writes.append(values)
        self.__dict__.update(values)

    def _lock_outbox(self):
        return True

    def _queued(self, mail):
        self.mail_id = mail
        self.state = "pending"
        self.next_attempt_on = False

    def _reconcile_mail(self):
        return method("notification_outbox.py", "_reconcile_mail")(self)


class TestNotificationOutbox(unittest.TestCase):
    def test_cron_requeues_due_failure_without_smtp(self):
        log = Log(Mail("exception"))
        log.state = "failed"
        log.next_attempt_on = NOW - timedelta(minutes=1)
        log._retry_queued_email = lambda: method("notification_outbox.py", "_retry_queued_email")(log)
        class Env:
            cr = SimpleNamespace(savepoint=lambda: nullcontext())
        queries = []
        model = SimpleNamespace(env=Env())
        model.sudo = lambda: model
        model.search = lambda domain, **kwargs: queries.append((domain, kwargs)) or [log]
        method("notification_outbox.py", "_cron_reconcile_outbox")(model)
        self.assertEqual(log.mail_id.state, "outgoing")
        self.assertEqual(queries[0][1]["limit"], 200)
        self.assertIn(("target_model", "!=", "federation.communication.delivery"), queries[0][0])

    def test_cron_skips_busy_delivery(self):
        log = Log(Mail("exception"))
        log._lock_outbox = lambda: False
        class Env:
            cr = SimpleNamespace(savepoint=lambda: nullcontext())
        model = SimpleNamespace(env=Env())
        model.sudo = lambda: model
        model.search = lambda *args, **kwargs: [log]
        method("notification_outbox.py", "_cron_reconcile_outbox")(model)
        self.assertEqual(log.writes, [])
        self.assertEqual(log.mail_id.writes, [])

    def test_direct_fallback_delegates_to_shared_queue(self):
        calls = []
        dispatcher = SimpleNamespace(
            _unique_emails=lambda emails: list(dict.fromkeys(emails)),
            queue_direct_email=lambda *args, **kwargs: calls.append((args, kwargs)) or "queued",
        )
        result = method("notification_dispatcher.py", "_send_direct_email_or_log")(
            dispatcher, "record", "subject", "body", "log", ["a@test", "a@test"])
        self.assertEqual(result, "queued")
        self.assertEqual(calls[0][0][-1], "a@test")

    def test_result_routing_reads_both_teams_with_elevated_source(self):
        home = SimpleNamespace(email="home@test", club_id=SimpleNamespace(email="home-club@test"))
        away = SimpleNamespace(email="away@test", club_id=SimpleNamespace(email="away-club@test"))
        elevated = SimpleNamespace(home_team_id=home, away_team_id=away)
        class Match:
            name = "Result"
            def sudo(self):
                return elevated
            @property
            def home_team_id(self):
                raise PermissionError("caller cannot read private team contact")
            @property
            def away_team_id(self):
                raise PermissionError("caller cannot read private team contact")
        match = Match()
        calls = []
        dispatcher = SimpleNamespace(_send_email_or_log=lambda *args: calls.append(args) or "queued")
        result = method("notification_dispatcher.py", "send_result_approved")(dispatcher, match)
        self.assertEqual(result, "queued")
        self.assertIs(calls[0][0], match)
        self.assertEqual(calls[0][-1], ["home@test", "home-club@test", "away@test", "away-club@test"])

    def test_email_routing_deduplicates_and_queues(self):
        calls = []
        unique = method("notification_dispatcher.py", "_unique_emails")
        dispatcher = SimpleNamespace(
            _unique_emails=lambda emails: unique(None, emails),
            send_email_template=lambda *args, **kwargs: calls.append((args, kwargs)) or "queued",
        )
        result = method("notification_dispatcher.py", "_send_email_or_log")(
            dispatcher, "record", "template", "name", [" a@test ", "a@test", "", None])
        self.assertEqual(result, "queued")
        self.assertEqual(calls[0][1]["email_to"], ["a@test"])

    def test_no_recipient_records_failure_instead_of_queueing(self):
        calls = []
        dispatcher = SimpleNamespace(
            _unique_emails=lambda emails: [],
            _log_missing_recipients=lambda *args: calls.append(args) or "failed",
            send_email_template=lambda *args, **kwargs: self.fail("empty recipients queued"),
        )
        result = method("notification_dispatcher.py", "_send_email_or_log")(
            dispatcher, "record", "template", "name", [])
        self.assertEqual(result, "failed")
        self.assertEqual(calls[0][2], "email")

    def test_structure_prohibits_immediate_send(self):
        self.assertEqual(violations(), [])

    def test_queued_is_not_sent(self):
        log = Log(Mail())
        log._reconcile_mail()
        self.assertEqual(log.state, "pending")
        self.assertFalse(log.sent_on)
        self.assertEqual(log.writes, [])

    def test_observed_sent_state_is_recorded_once(self):
        log = Log(Mail("sent"))
        log._reconcile_mail()
        self.assertEqual(log.state, "sent")
        self.assertEqual(log.sent_on, NOW)
        log.writes.clear()
        log._reconcile_mail()
        self.assertEqual(log.writes, [])

    def test_transient_failure_schedules_retry_without_sending(self):
        log = Log(Mail("exception"))
        log._reconcile_mail()
        self.assertEqual(log.state, "failed")
        self.assertEqual(log.next_attempt_on, NOW + timedelta(minutes=5))
        self.assertEqual(log.mail_id.writes, [])

    def test_reconciliation_does_not_postpone_existing_retry(self):
        log = Log(Mail("exception"))
        log._reconcile_mail()
        due = log.next_attempt_on
        log._reconcile_mail()
        self.assertEqual(log.next_attempt_on, due)

    def test_retry_budget_is_bounded(self):
        log = Log(Mail("exception"))
        log.attempt_count = 3
        log._reconcile_mail()
        self.assertFalse(log.next_attempt_on)

    def test_permanent_failure_is_not_automatically_retried(self):
        log = Log(Mail("exception"))
        log.mail_id.failure_reason = "Invalid recipient"
        log._reconcile_mail()
        self.assertFalse(log.next_attempt_on)

    def test_retry_reuses_mail_identity(self):
        log = Log(Mail("exception"))
        log.state = "failed"
        mail = log.mail_id
        method("notification_outbox.py", "_retry_queued_email")(log)
        self.assertIs(log.mail_id, mail)
        self.assertEqual(mail.state, "outgoing")
        self.assertEqual(log.state, "pending")

    def test_missing_previously_queued_mail_is_not_recreated(self):
        log = Log()
        with self.assertRaisesRegex(ValueError, "Previously queued mail is missing"):
            method("notification_outbox.py", "_retry_queued_email")(log)

    def test_cancelled_mail_is_not_requeued(self):
        log = Log(Mail("cancel"))
        with self.assertRaisesRegex(ValueError, "Cancelled"):
            method("notification_outbox.py", "_retry_queued_email")(log)
        self.assertEqual(log.mail_id.writes, [])

    def test_busy_transport_prevents_retry(self):
        log = Log(Mail("exception"))
        log._lock_outbox = lambda: False
        with self.assertRaisesRegex(ValueError, "being processed"):
            method("notification_outbox.py", "_retry_queued_email")(log)
        self.assertEqual(log.mail_id.writes, [])

    def test_template_helper_explicitly_queues_and_retains_mail(self):
        mail = Mail()
        calls = []
        template = SimpleNamespace(sudo=lambda: template,
            send_mail=lambda record_id, **kwargs: calls.append(kwargs) or mail.id)
        mail_model = SimpleNamespace(sudo=lambda: mail_model, browse=lambda ident: mail)
        class Env(dict):
            cr = SimpleNamespace(savepoint=lambda: nullcontext())
            def ref(self, *args, **kwargs):
                return template
        env = Env({"mail.mail": mail_model})
        service = SimpleNamespace(env=env)
        log = Log()
        log.template_xmlid = "test.template"
        log._queue_failed = lambda error: self.fail(str(error))
        method("notification_service.py", "_queue_template")(
            service, log, SimpleNamespace(id=9), email_to="recipient@example.test")
        self.assertFalse(calls[0]["force_send"])
        self.assertFalse(calls[0]["email_values"]["auto_delete"])
        self.assertEqual(log.state, "pending")

    def test_template_failure_is_returned_as_evidence(self):
        class Env:
            cr = SimpleNamespace(savepoint=lambda: nullcontext())
            def ref(self, *args, **kwargs):
                raise RuntimeError("render failed")
        log = Log()
        log.template_xmlid = "test.template"
        failures = []
        log._queue_failed = lambda error: failures.append(str(error))
        result = method("notification_service.py", "_queue_template")(
            SimpleNamespace(env=Env()), log, SimpleNamespace(id=9))
        self.assertIs(result, log)
        self.assertEqual(failures, ["render failed"])


if __name__ == "__main__":
    unittest.main()
