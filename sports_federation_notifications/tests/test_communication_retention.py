from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models.communication_retention import (
    MIN_RETENTION_DAYS,
    RETENTION_PARAMETER,
    retention_days_from_value,
)


@tagged("post_install", "-at_install", "sf_notification_retention")
class TestCommunicationRetention(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create({"name": "Retention User", "login": "retention.user@example.test"})
        )
        cls.Receipt = cls.env["federation.communication.receipt"].sudo()
        cls.Evidence = cls.env["federation.retention.evidence"].sudo()
        cls.now = fields.Datetime.now()
        cls.old = cls.now - timedelta(days=400)

    def _set_days(self, value):
        self.env["ir.config_parameter"].sudo().set_param(RETENTION_PARAMETER, value)

    def _receipt(self, key, **values):
        base = {
            "name": "Retention receipt",
            "event_key": key,
            "recipient_id": self.user.id,
            "kind": "due_soon",
            "target_model": "federation.operation.task",
            "target_res_id": 1,
            "occurred_on": self.old,
            "available_on": self.old,
        }
        base.update(values)
        return self.Receipt.create(base)

    def _delivery(self, receipt, key, state):
        return (
            self.env["federation.communication.delivery"]
            .sudo()
            .create(
                {
                    "name": "Retention delivery",
                    "delivery_key": key,
                    "recipient_id": self.user.id,
                    "receipt_ids": [(6, 0, receipt.ids)],
                    "state": state,
                }
            )
        )

    def _latest_evidence(self):
        return self.Evidence.search(
            [("policy", "=", "participant_inbox")], order="id desc", limit=1
        )

    def test_parameter_parsing(self):
        self.assertEqual(retention_days_from_value(False), (0, False))
        self.assertEqual(retention_days_from_value("0"), (0, False))
        self.assertEqual(retention_days_from_value("365"), (365, False))
        days, problem = retention_days_from_value(str(MIN_RETENTION_DAYS - 1))
        self.assertEqual(days, 0)
        self.assertIn("below the minimum", problem)
        days, problem = retention_days_from_value("one year")
        self.assertEqual(days, 0)
        self.assertTrue(problem)

    def test_nothing_is_deleted_without_a_configured_period(self):
        self._set_days("")
        receipt = self._receipt("ret-disabled", expired_on=self.old)
        self.Receipt._cron_purge_inbox()
        self.assertTrue(receipt.exists())
        evidence = self._latest_evidence()
        self.assertEqual(evidence.status, "passed")
        self.assertTrue(evidence.dry_run)
        self.assertEqual(evidence.deleted_count, 0)

    def test_period_below_minimum_is_reported_and_deletes_nothing(self):
        self._set_days(str(MIN_RETENTION_DAYS - 1))
        receipt = self._receipt("ret-too-short", expired_on=self.old)
        self.Receipt._cron_purge_inbox()
        self.assertTrue(receipt.exists())
        evidence = self._latest_evidence()
        self.assertEqual(evidence.status, "failed")
        self.assertIn("below the minimum", evidence.operator_message)

    def test_closed_items_past_the_period_are_deleted_with_finished_deliveries(self):
        self._set_days("365")
        expired = self._receipt("ret-expired", expired_on=self.old)
        acted = self._receipt("ret-acted", acted_on=self.old)
        superseded = self._receipt("ret-superseded", superseded_on=self.old)
        delivery = self._delivery(acted, "ret-acted-delivery", "sent")
        self.assertEqual(acted.lifecycle_state, "acted")

        self.Receipt._cron_purge_inbox()

        self.assertFalse(expired.exists())
        self.assertFalse(acted.exists())
        self.assertFalse(superseded.exists())
        self.assertFalse(delivery.exists())
        evidence = self._latest_evidence()
        self.assertEqual(evidence.status, "passed")
        self.assertEqual(evidence.deleted_count, 4)

    def test_open_or_recent_items_are_kept(self):
        self._set_days("365")
        unresolved = self._receipt("ret-open")
        seen = self._receipt("ret-seen", seen_on=self.old)
        recent = self._receipt("ret-recent", expired_on=self.now - timedelta(days=10))
        self.Receipt._cron_purge_inbox()
        self.assertTrue(unresolved.exists())
        self.assertTrue(seen.exists())
        self.assertTrue(recent.exists())

    def test_items_with_a_delivery_needing_attention_are_kept(self):
        self._set_days("365")
        receipt = self._receipt("ret-failed", superseded_on=self.old)
        delivery = self._delivery(receipt, "ret-failed-delivery", "failed")
        self.Receipt._cron_purge_inbox()
        self.assertTrue(receipt.exists())
        self.assertTrue(delivery.exists())

    def test_shared_delivery_is_kept_while_another_item_uses_it(self):
        self._set_days("365")
        old_item = self._receipt("ret-shared-old", expired_on=self.old)
        open_item = self._receipt("ret-shared-open")
        delivery = self._delivery(old_item | open_item, "ret-shared", "sent")
        self.Receipt._cron_purge_inbox()
        self.assertFalse(old_item.exists())
        self.assertTrue(open_item.exists())
        self.assertTrue(delivery.exists())
