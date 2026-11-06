from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.identity_backfill import match_key


@tagged("post_install", "-at_install", "sf_member_services")
class TestIdentityBackfill(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.reviewer = (
            env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Backfill reviewer",
                    "login": "backfill-reviewer",
                    "group_ids": [
                        (
                            6,
                            0,
                            [
                                env.ref("base.group_user").id,
                                env.ref(
                                    "sports_federation_base.group_federation_manager"
                                ).id,
                            ],
                        )
                    ],
                }
            )
        )
        cls.outsider = (
            env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Backfill outsider",
                    "login": "backfill-outsider",
                    "group_ids": [(6, 0, [env.ref("base.group_user").id])],
                }
            )
        )
        cls.Candidate = env["federation.identity.candidate"].with_user(cls.reviewer)

    def _player(self, first, last, birth="2011-03-04"):
        return self.env["federation.player"].create(
            {"first_name": first, "last_name": last, "birth_date": birth}
        )

    def _legacy(self, players):
        """Make players look like data created before the identity review existed."""
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE federation_player SET family_match_key = NULL WHERE id IN %s",
            [tuple(players.ids)],
        )
        players.invalidate_recordset(["family_match_key"])

    def _lookalikes(self, tag):
        first = self._player("Legacy%s" % tag, "Original")
        second = self._player("Other%s" % tag, "Person")
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE federation_player SET first_name=%s, last_name=%s WHERE id=%s",
            [first.first_name, first.last_name, second.id],
        )
        second.invalidate_recordset(["first_name", "last_name"])
        return first, second

    def test_a_unique_legacy_player_is_keyed(self):
        player = self._player("Solo", "Legacy", "2010-05-06")
        self._legacy(player)
        stats = self.Candidate.run_backfill()
        player.invalidate_recordset(["family_match_key"])
        self.assertEqual(
            player.family_match_key, match_key("Solo", "Legacy", "2010-05-06")
        )
        self.assertGreaterEqual(stats["keyed"], 1)

    def test_lookalikes_are_queued_not_keyed_or_merged(self):
        first, second = self._lookalikes("A")
        self._legacy(first | second)
        self.Candidate.run_backfill()
        candidate = self.env["federation.identity.candidate"].search(
            [
                (
                    "match_key",
                    "=",
                    match_key(first.first_name, first.last_name, first.birth_date),
                )
            ]
        )
        self.assertEqual(candidate.player_ids, first | second)
        self.assertEqual(candidate.status, "open")
        first.invalidate_recordset(["family_match_key"])
        second.invalidate_recordset(["family_match_key"])
        self.assertFalse(first.family_match_key)
        self.assertFalse(second.family_match_key)
        self.assertFalse((first | second).sudo().mapped("family_duplicate_of_id"))

    def test_a_lookalike_of_an_already_keyed_player_is_queued(self):
        keyed, other = self._lookalikes("B")
        self._legacy(other)
        self.Candidate.run_backfill()
        candidate = self.env["federation.identity.candidate"].search(
            [
                (
                    "match_key",
                    "=",
                    match_key(keyed.first_name, keyed.last_name, keyed.birth_date),
                )
            ]
        )
        self.assertEqual(candidate.player_ids, keyed | other)

    def test_the_backfill_is_idempotent(self):
        first, second = self._lookalikes("C")
        self._legacy(first | second)
        self.Candidate.run_backfill()
        count = self.env["federation.identity.candidate"].search_count([])
        self.Candidate.run_backfill()
        self.assertEqual(
            self.env["federation.identity.candidate"].search_count([]), count
        )

    def test_players_without_a_birth_date_are_counted_not_keyed(self):
        player = self.env["federation.player"].create(
            {"first_name": "No", "last_name": "Birthdate"}
        )
        self._legacy(player)
        stats = self.Candidate.run_backfill()
        self.assertGreaterEqual(stats["needs_birth_date"], 1)
        player.invalidate_recordset(["family_match_key"])
        self.assertFalse(player.family_match_key)

    def test_only_membership_administrators_may_run_it(self):
        with self.assertRaises(AccessError):
            self.env["federation.identity.candidate"].with_user(
                self.outsider
            ).run_backfill()

    def test_review_opens_the_reviewed_identity_decision(self):
        first, second = self._lookalikes("D")
        self._legacy(first | second)
        self.Candidate.run_backfill()
        candidate = self.Candidate.search(
            [
                (
                    "match_key",
                    "=",
                    match_key(first.first_name, first.last_name, first.birth_date),
                )
            ]
        )
        action = candidate.action_review()
        self.assertEqual(action["res_model"], "federation.identity.review")
        review = self.env[action["res_model"]].browse(action["res_id"])
        self.assertEqual(
            {review.player_id, review.duplicate_player_id}, {first, second}
        )

    def test_dismissing_needs_a_reason_and_is_recorded(self):
        first, second = self._lookalikes("E")
        self._legacy(first | second)
        self.Candidate.run_backfill()
        candidate = self.Candidate.search(
            [
                (
                    "match_key",
                    "=",
                    match_key(first.first_name, first.last_name, first.birth_date),
                )
            ]
        )
        with self.assertRaises(ValidationError):
            candidate.action_dismiss()
        candidate.note = "Twins with the same name"
        candidate.action_dismiss()
        self.assertEqual(candidate.status, "dismissed")
        self.assertEqual(candidate.decided_by_id, self.reviewer)

    def test_a_dismissed_group_reopens_when_a_new_lookalike_appears(self):
        first, second = self._lookalikes("F")
        self._legacy(first | second)
        self.Candidate.run_backfill()
        key = match_key(first.first_name, first.last_name, first.birth_date)
        candidate = self.Candidate.search([("match_key", "=", key)])
        candidate.note = "Twins"
        candidate.action_dismiss()
        third = self._player("Third", "Person")
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE federation_player SET first_name=%s, last_name=%s, family_match_key=NULL WHERE id=%s",
            [first.first_name, first.last_name, third.id],
        )
        third.invalidate_recordset()
        self.Candidate.run_backfill()
        candidate.invalidate_recordset()
        self.assertEqual(candidate.status, "open")
        self.assertIn(third, candidate.player_ids)
