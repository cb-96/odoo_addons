from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestOperationJob(TransactionCase):
    def setUp(self):
        super().setUp()
        source = self.env["res.partner"].create({"name": "Job Source"})
        self.job = self.env["federation.operation.job"].create({
            "name": "Test Job", "source_model": source._name,
            "source_res_id": source.id, "correlation_id": "job-test-1",
            "max_attempts": 2,
        })

    def test_failure_uses_backoff_then_operator_action(self):
        self.job._start(); self.job._fail("temporary")
        self.assertEqual(self.job.state, "retry")
        self.assertTrue(self.job.next_retry_on)
        self.job._start(); self.job._fail("still broken")
        self.assertEqual(self.job.state, "operator_action")
        self.assertFalse(self.job.next_retry_on)

    def test_manual_retry_resets_terminal_job(self):
        self.job.write({"state": "operator_action", "attempt_count": 2})
        self.job.action_retry()
        self.assertEqual(self.job.state, "pending")
        self.assertEqual(self.job.attempt_count, 0)

    def test_stale_running_job_is_recovered(self):
        self.job.write({"state": "running", "attempt_count": 1,
                        "started_on": fields.Datetime.now() - timedelta(hours=1)})
        self.assertGreaterEqual(self.env["federation.operation.job"]._recover_stale(), 1)
        self.assertEqual(self.job.state, "retry")
