from odoo import api
from odoo.tests import tagged

from .test_competition_workspace_service import TestCompetitionWorkspaceService


@tagged("-at_install", "post_install", "sf_ws_true_concurrency")
class TestCompetitionWorkspaceTrueConcurrency(TestCompetitionWorkspaceService):
    """Committed, multi-cursor contracts for optimistic planner concurrency.

    These tests intentionally commit fixture data because another PostgreSQL cursor
    cannot observe TransactionCase data before commit. Run only on a disposable CI
    database through the dedicated sf_ws_true_concurrency tag.
    """

    def _committed_fixture(self, name):
        division, gameday = self._prepare_planned_division(name)
        match_ids = division.match_ids[:2].ids
        slot_ids = gameday.slot_ids.filtered(lambda slot: slot.state == "available")[
            :2
        ].ids
        revision = gameday.planner_revision
        self.env.cr.commit()
        return gameday.id, match_ids, slot_ids, revision

    def _environment(self, cursor):
        return api.Environment(cursor, self.env.uid, dict(self.env.context))

    def test_stale_writer_cannot_overwrite_newer_assignment(self):
        gameday_id, match_ids, slot_ids, stale_revision = self._committed_fixture(
            "True Concurrency Stale Writer"
        )
        with self.env.registry.cursor() as first_cursor:
            first_env = self._environment(first_cursor)
            first = first_env[
                "federation.competition.workspace.service"
            ].assign_match_to_slot(
                match_ids[0], slot_ids[0], expected_planner_revision=stale_revision
            )
            self.assertTrue(first["ok"])
            first_cursor.commit()

        with self.env.registry.cursor() as stale_cursor:
            stale_env = self._environment(stale_cursor)
            stale = stale_env[
                "federation.competition.workspace.service"
            ].assign_match_to_slot(
                match_ids[1], slot_ids[1], expected_planner_revision=stale_revision
            )
            self.assertFalse(stale["ok"])
            self.assertEqual(stale["conflict"]["code"], "stale_planner_revision")
            persisted = stale_env["federation.tournament.round"].browse(gameday_id)
            self.assertEqual(
                persisted.slot_ids.filtered(lambda slot: slot.match_id)
                .mapped("match_id")
                .ids,
                [match_ids[0]],
            )

    def test_two_writers_cannot_claim_the_same_slot(self):
        _gameday_id, match_ids, slot_ids, revision = self._committed_fixture(
            "True Concurrency Slot Claim"
        )
        with self.env.registry.cursor() as first_cursor:
            first_env = self._environment(first_cursor)
            result = first_env[
                "federation.competition.workspace.service"
            ].assign_match_to_slot(
                match_ids[0], slot_ids[0], expected_planner_revision=revision
            )
            self.assertTrue(result["ok"])
            first_cursor.commit()

        with self.env.registry.cursor() as second_cursor:
            second_env = self._environment(second_cursor)
            result = second_env[
                "federation.competition.workspace.service"
            ].assign_match_to_slot(match_ids[1], slot_ids[0])
            self.assertFalse(result["ok"])
            gameday = second_env["federation.tournament.round"].browse(_gameday_id)
            slot = gameday.slot_ids.filtered(lambda record: record.id == slot_ids[0])
            self.assertEqual(slot.match_id.id, match_ids[0])

    def test_idempotent_replay_does_not_create_a_second_operation(self):
        gameday_id, match_ids, slot_ids, revision = self._committed_fixture(
            "True Concurrency Idempotent Replay"
        )
        key = "ci-true-concurrency-assignment"
        with self.env.registry.cursor() as first_cursor:
            first_env = self._environment(first_cursor)
            first = first_env[
                "federation.competition.workspace.service"
            ].assign_match_to_slot(
                match_ids[0],
                slot_ids[0],
                expected_planner_revision=revision,
                idempotency_key=key,
            )
            self.assertTrue(first["ok"])
            first_cursor.commit()

        with self.env.registry.cursor() as replay_cursor:
            replay_env = self._environment(replay_cursor)
            replay = replay_env[
                "federation.competition.workspace.service"
            ].assign_match_to_slot(
                match_ids[0],
                slot_ids[0],
                expected_planner_revision=revision,
                idempotency_key=key,
            )
            self.assertTrue(replay["replayed"])
            operations = replay_env["federation.competition.planner.operation"].search(
                [
                    ("planner_root_round_id", "=", gameday_id),
                    ("batch_key", "=", f"idem:assign_match_to_slot:{key}"),
                    ("state", "=", "applied"),
                ]
            )
            self.assertEqual(len(operations), 1)
