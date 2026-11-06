from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_notification_lifecycle")
class TestCommunicationLifecycle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create({"name": "Lifecycle User", "login": "lifecycle.user@example.test"})
        )
        cls.other = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {"name": "Lifecycle Other", "login": "lifecycle.other@example.test"}
            )
        )
        cls.Receipt = cls.env["federation.communication.receipt"]

    def _receipt(self, key, **values):
        base = {
            "name": "Lifecycle receipt",
            "event_key": key,
            "recipient_id": self.user.id,
            "kind": "due_soon",
            "target_model": "federation.operation.task",
            "target_res_id": 1,
            "occurred_on": fields.Datetime.now(),
        }
        base.update(values)
        return self.Receipt.create(base)

    def _delivery(self, receipt, key, state):
        return (
            self.env["federation.communication.delivery"]
            .sudo()
            .create(
                {
                    "name": "Lifecycle delivery",
                    "delivery_key": key,
                    "recipient_id": self.user.id,
                    "receipt_ids": [(6, 0, receipt.ids)],
                    "state": state,
                }
            )
        )

    def test_a_new_item_is_created(self):
        self.assertEqual(self._receipt("lc-new").lifecycle_state, "created")

    def test_delivery_states_drive_the_lifecycle(self):
        receipt = self._receipt("lc-delivery")
        delivery = self._delivery(receipt, "lc-delivery-1", "pending")
        self.assertEqual(receipt.lifecycle_state, "queued")
        delivery.write({"state": "failed"})
        self.assertEqual(receipt.lifecycle_state, "failed")
        delivery.write({"state": "sent"})
        self.assertEqual(receipt.lifecycle_state, "delivered")

    def test_only_the_recipient_marks_an_item_seen(self):
        receipt = self._receipt("lc-seen")
        receipt.mark_seen(self.other)
        self.assertFalse(receipt.seen_on)
        receipt.mark_seen(self.user)
        self.assertTrue(receipt.seen_on)
        self.assertEqual(receipt.lifecycle_state, "seen")
        first = receipt.seen_on
        receipt.mark_seen(self.user)
        self.assertEqual(receipt.seen_on, first)

    def test_acknowledgement_counts_as_seen(self):
        receipt = self._receipt("lc-ack")
        receipt.sudo().write({"acknowledged_on": fields.Datetime.now()})
        self.assertEqual(receipt.lifecycle_state, "seen")

    def test_resolved_requirement_becomes_acted_upon(self):
        receipt = self._receipt("lc-acted")
        receipt.mark_seen(self.user)
        with patch.object(
            type(receipt), "_presentation", return_value={"complete": True}
        ):
            self.Receipt._cron_reconcile_lifecycle(batch=100000)
        self.assertEqual(receipt.lifecycle_state, "acted")
        self.assertTrue(receipt.acted_on)

    def test_seen_but_unresolved_stays_seen(self):
        receipt = self._receipt("lc-unresolved")
        receipt.mark_seen(self.user)
        with patch.object(
            type(receipt), "_presentation", return_value={"complete": False}
        ):
            self.Receipt._cron_reconcile_lifecycle(batch=100000)
        self.assertEqual(receipt.lifecycle_state, "seen")
        self.assertFalse(receipt.acted_on)

    def test_old_unresolved_items_expire(self):
        old = fields.Datetime.now() - timedelta(days=90)
        receipt = self._receipt("lc-expired", available_on=old)
        with patch.object(
            type(receipt), "_presentation", return_value={"complete": False}
        ):
            self.Receipt._cron_reconcile_lifecycle(batch=100000)
        self.assertEqual(receipt.lifecycle_state, "expired")

    def test_resolution_wins_over_expiry(self):
        old = fields.Datetime.now() - timedelta(days=90)
        receipt = self._receipt("lc-both", available_on=old)
        with patch.object(
            type(receipt), "_presentation", return_value={"complete": True}
        ):
            self.Receipt._cron_reconcile_lifecycle(batch=100000)
        self.assertEqual(receipt.lifecycle_state, "acted")

    def test_superseded_is_terminal(self):
        receipt = self._receipt("lc-superseded")
        receipt.sudo().write({"superseded_on": fields.Datetime.now()})
        self.assertEqual(receipt.lifecycle_state, "superseded")
        with patch.object(
            type(receipt), "_presentation", return_value={"complete": True}
        ):
            self.Receipt._cron_reconcile_lifecycle(batch=100000)
        self.assertEqual(receipt.lifecycle_state, "superseded")

    def test_a_failing_check_does_not_stop_the_batch(self):
        first = self._receipt("lc-batch-1")
        second = self._receipt("lc-batch-2")

        def presentation(record, user):
            if record == first:
                raise RuntimeError("boom")
            return {"complete": True}

        with patch.object(type(first), "_presentation", presentation):
            self.Receipt._cron_reconcile_lifecycle(batch=100000)
        self.assertEqual(second.lifecycle_state, "acted")
        self.assertNotEqual(first.lifecycle_state, "acted")

    def test_report_counts_by_state(self):
        self._receipt("lc-report-1").mark_seen(self.user)
        report = self.Receipt.lifecycle_report([("event_key", "=like", "lc-report-%")])
        self.assertEqual(report["totals"].get("seen"), 1)
