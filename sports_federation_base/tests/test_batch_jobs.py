from unittest.mock import patch

from psycopg2.errors import SerializationFailure

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.sports_federation_base import batch_jobs


@tagged("post_install", "-at_install", "sf_batch_jobs")
class TestBatchJobs(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clubs = cls.env["federation.club"].create(
            [{"name": "Batch Club %s" % index} for index in range(5)]
        )

    def test_a_failing_record_is_skipped_and_the_others_are_saved(self):
        bad = self.clubs[2]

        def rename(club):
            club.write({"name": club.name + " done"})
            if club == bad:
                raise ValidationError("broken record")

        done, failed = batch_jobs.process_each(
            self.clubs, rename, label="Test job", batch_size=2
        )
        self.assertEqual((done, failed), (4, 1))
        self.assertTrue(all(c.name.endswith("done") for c in self.clubs - bad))
        # The failing record's own change was rolled back with its savepoint.
        self.assertFalse(bad.name.endswith("done"))

    def test_concurrency_errors_are_raised_for_a_retry(self):
        def conflict(club):
            raise SerializationFailure("could not serialize")

        with self.assertRaises(SerializationFailure):
            batch_jobs.process_each(self.clubs, conflict, label="Test job")

    def test_chunks_cover_every_record_and_sum_counts(self):
        seen = []

        def handle(chunk):
            seen.append(len(chunk))
            return len(chunk)

        total = batch_jobs.for_each_chunk(self.clubs, handle, batch_size=2)
        self.assertEqual(total, 5)
        self.assertEqual(seen, [2, 2, 1])

    def test_no_commit_outside_scheduled_jobs_or_in_tests(self):
        self.assertFalse(batch_jobs.commits_between_batches(self.env))
        cron_env = self.env(context=dict(self.env.context, cron_id=1))
        # Even as a scheduled job, tests never commit.
        self.assertFalse(batch_jobs.commits_between_batches(cron_env))
        with patch.object(type(self.env.cr), "commit") as commit:
            batch_jobs.for_each_chunk(
                self.clubs.with_env(cron_env), lambda chunk: 0, batch_size=2
            )
        commit.assert_not_called()
