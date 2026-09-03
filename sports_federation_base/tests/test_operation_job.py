from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestOperationJob(TransactionCase):
    def setUp(self):
        super().setUp()
        source = self.env["res.partner"].create({"name": "Job Source"})
        self.job = self.env["federation.operation.job"].create(
            {
                "name": "Test Job",
                "source_model": source._name,
                "source_res_id": source.id,
                "correlation_id": "job-test-1",
                "max_attempts": 2,
            }
        )

    def test_failure_uses_backoff_then_operator_action(self):
        self.job._start()
        self.job._fail("temporary")
        self.assertEqual(self.job.state, "retry")
        self.assertTrue(self.job.next_retry_on)
        self.job._start()
        self.job._fail("still broken")
        self.assertEqual(self.job.state, "operator_action")
        self.assertFalse(self.job.next_retry_on)

    def test_manual_retry_resets_terminal_job(self):
        self.job.write({"state": "operator_action", "attempt_count": 2})
        self.job.action_retry()
        self.assertEqual(self.job.state, "pending")
        self.assertEqual(self.job.attempt_count, 0)

    def test_stale_running_job_is_recovered(self):
        self.job.write(
            {
                "state": "running",
                "attempt_count": 1,
                "started_on": fields.Datetime.now() - timedelta(hours=1),
            }
        )
        self.assertGreaterEqual(
            self.env["federation.operation.job"]._recover_stale(), 1
        )
        self.assertEqual(self.job.state, "retry")

    def test_ensure_job_is_idempotent_for_source_correlation(self):
        source = self.job._source()
        duplicate = self.env["federation.operation.job"].ensure_job(
            source, self.job.correlation_id, name="Do not replace", max_attempts=9
        )
        self.assertEqual(duplicate, self.job)
        self.assertEqual(duplicate.name, "Test Job")
        self.assertEqual(duplicate.max_attempts, 2)

    def test_non_retryable_failure_goes_directly_to_operator_action(self):
        self.job._start()
        self.job._fail("invalid payload", "data_validation", retryable=False)
        self.assertEqual(self.job.state, "operator_action")
        self.assertEqual(self.job.failure_category, "data_validation")
        self.assertFalse(self.job.next_retry_on)
        self.assertTrue(self.job.operator_action_on)

    def test_manual_retry_rejects_non_failed_job(self):
        with self.assertRaises(ValidationError):
            self.job.action_retry()
