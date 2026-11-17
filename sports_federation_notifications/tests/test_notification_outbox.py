from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_release_confidence")
class TestNotificationOutbox(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Outbox club",
                "code": "OUTBOX",
                "email": "outbox@example.test",
            }
        )

    def _queue(self):
        return self.env["federation.notification.service"].queue_direct_email(
            self.club,
            "Review work",
            "<p>Review work</p>",
            "recipient@example.test",
        )

    def test_business_action_does_not_send_smtp(self):
        Mail = self.env["mail.mail"]
        with patch.object(
            type(Mail), "send", side_effect=AssertionError("SMTP in business action")
        ):
            log = self._queue()
        self.assertEqual(log.state, "pending")
        self.assertTrue(log.mail_id)
        self.assertEqual(log.mail_id.state, "outgoing")
        self.assertFalse(log.sent_on)
        self.assertFalse(log.mail_id.auto_delete)

    def test_retry_preserves_mail_and_log(self):
        log = self._queue()
        mail_id, log_id = log.mail_id.id, log.id
        log.mail_id.write({"state": "exception", "failure_reason": "SMTP timeout"})
        log._reconcile_mail()
        self.assertEqual(log.state, "failed")
        log._retry_queued_email()
        self.assertEqual(log.mail_id.id, mail_id)
        self.assertEqual(log.id, log_id)
        self.assertEqual(log.mail_id.state, "outgoing")
        self.assertEqual(log.state, "pending")

    def test_transport_state_is_required_for_sent_evidence(self):
        log = self._queue()
        log._reconcile_mail()
        self.assertEqual(log.state, "pending")
        log.mail_id.write({"state": "sent"})
        log._reconcile_mail()
        self.assertEqual(log.state, "sent")
        self.assertTrue(log.sent_on)

    def test_due_retry_cron_does_not_send(self):
        log = self._queue()
        log.mail_id.write({"state": "exception", "failure_reason": "SMTP timeout"})
        log.write({"attempt_count": 1})
        log._reconcile_mail()
        log.write({"next_attempt_on": fields.Datetime.now() - timedelta(minutes=1)})
        with patch.object(
            type(self.env["mail.mail"]),
            "send",
            side_effect=AssertionError("cron sent SMTP"),
        ):
            self.env["federation.notification.log"]._cron_reconcile_outbox()
        self.assertEqual(log.state, "pending")
        self.assertEqual(log.mail_id.state, "outgoing")

    def test_missing_mail_requires_operator_review(self):
        log = self._queue()
        log.mail_id.unlink()
        log.invalidate_recordset()
        with self.assertRaises(ValidationError):
            log._retry_queued_email()
        log._reconcile_mail()
        self.assertEqual(log.state, "failed")
        self.assertFalse(log.next_attempt_on)

    def test_queued_pending_log_survives_retention(self):
        log = self._queue()
        self.env.cr.execute(
            "UPDATE federation_notification_log SET create_date = %s WHERE id = %s",
            [fields.Datetime.now() - timedelta(days=40), log.id],
        )
        log.invalidate_recordset()
        self.env["federation.notification.log"]._purge_retained_logs()
        self.assertTrue(log.exists())

    def test_template_render_failure_rolls_back_only_side_effect(self):
        Template = self.env["mail.template"]
        template = Template.create(
            {
                "name": "Outbox render test",
                "model_id": self.env["ir.model"]._get_id(self.club._name),
                "subject": "Outbox",
                "body_html": "<p>Outbox</p>",
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": "sports_federation_notifications",
                "name": "outbox_test_template",
                "model": template._name,
                "res_id": template.id,
            }
        )
        self.club.write({"name": "Business decision retained"})
        Mail = self.env["mail.mail"]
        before = Mail.search_count([])

        def fail_after_create(recordset, *args, **kwargs):
            Mail.create(
                {"subject": "Must roll back", "email_to": "recipient@example.test"}
            )
            raise RuntimeError("render failed")

        with patch.object(type(Template), "send_mail", fail_after_create):
            log = self.env["federation.notification.service"].send_email_template(
                self.club,
                "sports_federation_notifications.outbox_test_template",
                email_to="recipient@example.test",
            )
        self.assertEqual(log.state, "failed")
        self.assertFalse(log.mail_id)
        self.assertEqual(Mail.search_count([]), before)
        self.assertEqual(self.club.name, "Business decision retained")

    def test_portal_user_cannot_retry(self):
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Outbox portal",
                    "login": "outbox-portal@example.test",
                    "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
                }
            )
        )
        log = self._queue()
        log.write({"state": "failed"})
        with self.assertRaises(AccessError):
            log.with_user(user).action_queue_retry()
