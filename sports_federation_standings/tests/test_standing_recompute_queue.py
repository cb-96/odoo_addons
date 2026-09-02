from datetime import timedelta
from unittest.mock import patch

from odoo import fields

from odoo.tests.common import TransactionCase


class TestStandingRecomputeQueue(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.has_result_control = (
            "include_in_official_standings" in cls.env["federation.match"]._fields
        )
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Queue Club",
                "code": "QCLB",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Queue Season",
                "code": "QSEASON",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Queue Tournament",
                "code": "QTOUR",
                "season_id": cls.season.id,
                "date_start": "2026-06-01",
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Queue Rule Set",
                "code": "QRS",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "Queue Team A",
                "club_id": cls.club.id,
                "code": "QTA",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "Queue Team B",
                "club_id": cls.club.id,
                "code": "QTB",
            }
        )
        cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_a.id,
            }
        )
        cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_b.id,
            }
        )

    def _match_vals(self):
        vals = {
            "tournament_id": self.tournament.id,
            "home_team_id": self.team_a.id,
            "away_team_id": self.team_b.id,
            "home_score": 2,
            "away_score": 1,
            "state": "done",
        }
        if self.has_result_control:
            vals["include_in_official_standings"] = True
        return vals

    def _create_standing(self):
        return self.env["federation.standing"].create(
            {
                "name": "Queue Standing",
                "tournament_id": self.tournament.id,
                "rule_set_id": self.rule_set.id,
            }
        )

    def test_queue_request_replays_for_same_idempotency_key(self):
        standing = self._create_standing()
        queue_model = self.env["federation.standing.recompute.job"]

        first = queue_model.request_recompute(
            standing,
            idempotency_key="standing-q-1",
            correlation_id="corr-q-1",
        )
        second = queue_model.request_recompute(
            standing,
            idempotency_key="standing-q-1",
            correlation_id="corr-q-2",
        )

        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["job"].id, second["job"].id)
        self.assertEqual(first["job"].correlation_id, "corr-q-1")

    def test_queue_cron_recomputes_standing(self):
        self.env["federation.match"].create(self._match_vals())
        standing = self._create_standing()
        queue_model = self.env["federation.standing.recompute.job"]
        queue_model.request_recompute(
            standing,
            idempotency_key="standing-q-2",
            correlation_id="corr-q-2",
        )

        processed = queue_model._cron_process_queue()
        standing.invalidate_recordset(["state", "line_ids"])
        job = queue_model.search(
            [
                ("standing_id", "=", standing.id),
                ("idempotency_key", "=", "standing-q-2"),
            ],
            limit=1,
        )

        self.assertEqual(processed, 1)
        self.assertEqual(job.state, "done")
        self.assertEqual(standing.state, "computed")
        self.assertTrue(standing.line_ids)

    def test_queue_failure_is_visible_and_retriable(self):
        standing = self._create_standing()
        queue_model = self.env["federation.standing.recompute.job"]
        queue_model.request_recompute(
            standing,
            idempotency_key="standing-q-3",
            correlation_id="corr-q-3",
        )

        def _broken_action_recompute(self):
            raise RuntimeError("boom")

        with patch.object(type(standing), "action_recompute", _broken_action_recompute):
            queue_model._cron_process_queue()

        job = queue_model.search(
            [
                ("standing_id", "=", standing.id),
                ("idempotency_key", "=", "standing-q-3"),
            ],
            limit=1,
        )
        self.assertEqual(job.state, "failed")
        self.assertIn("boom", job.last_error)
        self.assertGreaterEqual(standing.recompute_failed_count, 1)

        job.write({"state": "pending", "next_retry_on": False})
        queue_model._cron_process_queue()

        job.invalidate_recordset(["state"])
        self.assertEqual(job.state, "done")

    def test_exhausted_job_moves_to_dead_letter_and_can_be_retried(self):
        standing = self._create_standing()
        job = self.env["federation.standing.recompute.job"].create(
            {
                "standing_id": standing.id,
                "correlation_id": "dead-letter-1",
                "attempt_count": 2,
                "max_attempts": 3,
            }
        )
        with patch.object(
            type(standing), "action_recompute", side_effect=RuntimeError("boom")
        ):
            self.assertFalse(job._process_single_job())
        self.assertEqual(job.state, "dead_letter")
        self.assertFalse(job.next_retry_on)
        self.assertTrue(job.dead_lettered_on)
        job.action_retry()
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.attempt_count, 0)

    def test_stale_running_job_is_recovered(self):
        standing = self._create_standing()
        job = self.env["federation.standing.recompute.job"].create(
            {
                "standing_id": standing.id,
                "correlation_id": "stale-1",
                "state": "running",
                "started_on": fields.Datetime.now() - timedelta(hours=1),
            }
        )
        self.assertEqual(
            self.env["federation.standing.recompute.job"]._recover_stale_running_jobs(),
            1,
        )
        self.assertEqual(job.state, "failed")
        self.assertTrue(job.next_retry_on)
