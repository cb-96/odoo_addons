"""Installed authorization, transaction, pagination and retention regressions."""

from datetime import timedelta
from unittest.mock import patch

from psycopg2.errors import SerializationFailure
from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_release_confidence")
class TestNotificationOperations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env.ref("sports_federation_base.group_federation_user")
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Scoped notification reader",
                    "login": "scoped-notification-reader",
                    "group_ids": [(6, 0, [group.id])],
                }
            )
        )
        cls.other = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Other notification reader",
                    "login": "other-notification-reader",
                    "group_ids": [(6, 0, [group.id])],
                }
            )
        )
        cls.club = cls.env["federation.club"].create(
            {"name": "Notification boundary club"}
        )
        cls.service = cls.env["federation.notification.service"]

    def log(self, **values):
        return self.env["federation.notification.log"].create(
            {
                "name": "Notification evidence",
                "notification_type": "email",
                **values,
            }
        )

    def receipt(self, key, **values):
        return (
            self.env["federation.communication.receipt"]
            .sudo()
            .create(
                {
                    "name": "Inbox evidence",
                    "event_key": key,
                    "recipient_id": self.user.id,
                    "occurred_on": fields.Datetime.now(),
                    "kind": "due_soon",
                    "target_model": "federation.operation.task",
                    "target_res_id": 1,
                    **values,
                }
            )
        )

    def age(self, record, days=400):
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE "%s" SET create_date = %%s WHERE id = %%s' % record._table,
            [fields.Datetime.now() - timedelta(days=days), record.id],
        )
        record.invalidate_recordset()

    def queue(self):
        return self.service.queue_direct_email(
            self.club, "Work", "<p>Work</p>", "test@example.test"
        )

    def test_unrelated_legacy_log_denied(self):
        log = self.log(
            target_model="federation.club",
            target_res_id=self.club.id,
            recipient_partner_id=self.other.partner_id.id,
        )
        with self.assertRaises(AccessError):
            log.with_user(self.user).read(["name"])

    def test_unassigned_legacy_log_denied(self):
        with self.assertRaises(AccessError):
            self.log().with_user(self.user).read(["name"])

    def test_intended_partner_can_read_log(self):
        log = self.log(recipient_partner_id=self.user.partner_id.id)
        self.assertEqual(log.with_user(self.user).read(["name"])[0]["name"], log.name)

    def test_target_compute_respects_caller_access(self):
        log = self.log(
            recipient_partner_id=self.user.partner_id.id,
            target_model="res.users",
            target_res_id=self.other.id,
        )
        target = self.env["res.users"]
        with patch.object(
            type(target), "check_access", side_effect=AccessError("denied")
        ):
            log.with_user(self.user)._compute_target_display_name()
            self.assertFalse(log.with_user(self.user).target_display_name)

    def test_log_create_failure_preserves_business_write(self):
        self.club.name = "Decision preserved"
        logs = self.env["federation.notification.log"]
        with patch.object(
            type(logs), "create", side_effect=RuntimeError("log store failed")
        ):
            result = self.queue()
        self.assertFalse(result)
        self.assertEqual(self.club.name, "Decision preserved")

    def test_routing_failure_is_recorded(self):
        self.club.name = "Routing decision preserved"
        dispatcher = self.env["federation.notification.dispatcher"]
        with patch.object(
            type(dispatcher),
            "_get_season_registration_recipient",
            side_effect=RuntimeError("routing failed"),
        ):
            log = dispatcher.send_season_registration_confirmed(
                self.env["federation.season.registration"].browse()
            )
        self.assertEqual(log.state, "failed")
        self.assertEqual(self.club.name, "Routing decision preserved")

    def test_savepoint_rolls_back_notification_changes_only(self):
        self.club.name = "Authoritative decision"

        def fail():
            self.club.name = "Side effect to undo"
            raise RuntimeError("failed")

        result = self.service._run_notification_effect(fail, source=self.club)
        self.assertEqual(result.state, "failed")
        self.assertEqual(self.club.name, "Authoritative decision")

    def test_framework_retry_propagates(self):
        def fail():
            raise SerializationFailure("retry transaction")

        with self.assertRaises(SerializationFailure):
            self.service._run_notification_effect(fail)

    def test_inbox_cursor_has_no_overlap(self):
        receipts = [self.receipt("cursor-%s" % i) for i in range(45)]
        with patch.object(
            type(receipts[0]), "_presentation", return_value={"task_state": "open"}
        ):
            service = self.service.with_user(self.user)
            first = service._inbox_page(self.user)
            second = service._inbox_page(self.user, before=first["next_before"])
        self.assertEqual(len(first["items"]), 20)
        self.assertEqual(len(second["items"]), 20)
        self.assertFalse(
            {row["receipt"].id for row in first["items"]}
            & {row["receipt"].id for row in second["items"]}
        )

    def test_revoked_window_retains_continuation(self):
        receipts = [self.receipt("revoked-%s" % i) for i in range(205)]
        with patch.object(
            type(receipts[0]), "_presentation", side_effect=AccessError("revoked")
        ) as present:
            page = self.service.with_user(self.user)._inbox_page(self.user)
        self.assertEqual(present.call_count, 200)
        self.assertFalse(page["items"])
        self.assertTrue(page["next_before"])

    def test_inbox_cannot_impersonate_other_user(self):
        with self.assertRaises(AccessError):
            self.service.with_user(self.user)._inbox_page(self.other)

    def test_page_size_is_capped(self):
        receipts = [self.receipt("capped-%s" % i) for i in range(30)]
        with patch.object(type(receipts[0]), "_presentation", return_value={}):
            page = self.service.with_user(self.user)._inbox_page(self.user, limit=1000)
        self.assertEqual(len(page["items"]), 20)

    def test_sent_log_and_owned_mail_clean_up_together(self):
        log = self.queue()
        mail = log.mail_id
        mail.state = "sent"
        log._reconcile_mail()
        self.age(log)
        self.env["federation.notification.log"]._purge_retained_logs()
        self.assertFalse(log.exists())
        self.assertFalse(mail.exists())

    def test_failed_mail_keeps_log_and_content(self):
        log = self.queue()
        mail = log.mail_id
        mail.state = "exception"
        log.state = "failed"
        self.age(log)
        self.env["federation.notification.log"]._purge_retained_logs()
        self.assertTrue(log.exists())
        self.assertTrue(mail.exists())

    def test_shared_mail_kept_until_last_log_expires(self):
        first = self.queue()
        mail = first.mail_id
        mail.state = "sent"
        first._reconcile_mail()
        second = self.log(mail_id=mail.id, state="sent")
        self.age(first)
        self.env["federation.notification.log"]._purge_retained_logs()
        self.assertTrue(mail.exists())
        self.age(second)
        self.env["federation.notification.log"]._purge_retained_logs()
        self.assertFalse(mail.exists())

    def test_unrelated_mail_is_never_swept(self):
        mail = self.env["mail.mail"].create({"subject": "Unrelated", "state": "sent"})
        self.assertEqual(mail._purge_notification_orphans(), 0)
        self.assertTrue(mail.exists())

    def test_owned_orphan_retry_cleanup_records_evidence(self):
        mail = self.env["mail.mail"].create(
            {
                "subject": "Owned orphan",
                "state": "sent",
                "federation_notification_owned": True,
            }
        )
        self.age(mail)
        self.env["federation.notification.log"]._cron_purge_owned_mail()
        self.assertFalse(mail.exists())
        evidence = self.env["federation.retention.evidence"].search(
            [("policy", "=", "notification_mail_content")], order="id desc", limit=1
        )
        self.assertEqual(evidence.status, "passed")
        self.assertGreaterEqual(evidence.deleted_count, 1)

    def test_live_delivery_protects_mail_and_log(self):
        log = self.queue()
        mail = log.mail_id
        mail.state = "sent"
        log._reconcile_mail()
        receipt = self.receipt("shared-delivery")
        self.env["federation.communication.delivery"].create(
            {
                "name": "Shared delivery",
                "delivery_key": "shared-delivery",
                "recipient_id": self.user.id,
                "receipt_ids": [(6, 0, receipt.ids)],
                "mail_id": mail.id,
                "log_id": log.id,
                "state": "sent",
            }
        )
        self.age(log)
        self.env["federation.notification.log"]._purge_retained_logs()
        self.assertTrue(log.exists())
        self.assertTrue(mail.exists())

    def test_closed_inbox_cleans_delivery_mail_and_log(self):
        log = self.queue()
        mail = log.mail_id
        mail.state = "sent"
        log._reconcile_mail()
        old = fields.Datetime.now() - timedelta(days=400)
        receipt = self.receipt("closed-delivery", expired_on=old)
        delivery = self.env["federation.communication.delivery"].create(
            {
                "name": "Closed delivery",
                "delivery_key": "closed-delivery",
                "recipient_id": self.user.id,
                "receipt_ids": [(6, 0, receipt.ids)],
                "mail_id": mail.id,
                "log_id": log.id,
                "state": "sent",
            }
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation_notifications.inbox_retention_days", "365"
        )
        self.env["federation.communication.receipt"]._purge_retained_inbox()
        self.assertFalse(receipt.exists())
        self.assertFalse(delivery.exists())
        self.assertFalse(log.exists())
        self.assertFalse(mail.exists())
