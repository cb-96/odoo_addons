from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_handoffs")
class TestParticipantHandoff(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Registration Selection Season",
                "date_start": "2025-09-01",
                "date_end": "2026-06-30",
            }
        )
        cls.competition = cls.env["federation.competition"].create(
            {
                "name": "Registration Selection Competition",
                "competition_type": "league",
            }
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Registration Selection Edition",
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
            }
        )
        cls.division = cls.env["federation.tournament"].create(
            {
                "name": "Senior Men Division",
                "edition_id": cls.edition.id,
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
                "date_start": "2025-10-01",
                "category": "senior",
                "gender": "male",
            }
        )
        cls.club = cls.env["federation.club"].create(
            {"name": "Registration Selection Club"}
        )
        cls.window = cls.env["federation.registration.window"].create(
            {
                "name": "Senior Men Registration",
                "edition_id": cls.edition.id,
                "division_id": cls.division.id,
            }
        )

    def _make_team(self, name, category="senior", gender="male"):
        return self.env["federation.team"].create(
            {
                "name": name,
                "club_id": self.club.id,
                "category": category,
                "gender": gender,
            }
        )

    def _approved(self):
        teams = self._make_team("Handoff A") | self._make_team("Handoff B")
        entries = self.env["federation.competition.entry"].create([
            {"window_id": self.window.id, "team_id": team.id, "state": "approved"}
            for team in teams
        ])
        self.window.action_open()
        self.window.action_close()
        return teams, entries

    def test_finalization_is_idempotent_and_links_participants(self):
        teams, entries = self._approved()
        digest = self.window._entry_digest()
        self.window.action_finalize(expected_digest=digest)
        snapshot = self.window.participant_set_id
        self.window.action_finalize(expected_digest=digest)
        self.assertEqual(self.window.participant_set_id, snapshot)
        participants = self.env["federation.tournament.participant"].search([
            ("tournament_id", "=", self.division.id), ("state", "=", "confirmed"),
        ])
        self.assertEqual(set(participants.team_id.ids), set(teams.ids))
        self.assertEqual(set(participants.source_entry_id.ids), set(entries.ids))
        self.assertEqual(participants.mapped("source_participant_set_id"), snapshot)

    def test_stale_review_rejected_without_snapshot(self):
        teams, entries = self._approved()
        digest = self.window._entry_digest()
        entries[:1].write({"seed": 7})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.window.action_finalize(expected_digest=digest)
        self.assertFalse(self.window.participant_set_id)

    def test_finalized_entry_and_snapshot_cannot_be_edited(self):
        teams, entries = self._approved()
        self.window.action_finalize()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            entries[:1].write({"state": "rejected"})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.window.participant_set_id.line_ids[:1].write({"seed": 9})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.window.action_open()

    def test_amendment_preserves_previous_snapshot(self):
        teams, entries = self._approved()
        self.window.action_finalize()
        old = self.window.participant_set_id
        replacement = self._make_team("Handoff Replacement")
        new = self.window.amend_finalized_teams((teams[:1] | replacement).ids, "Team replacement approved", old.id)
        self.assertNotEqual(new, old)
        self.assertEqual(old.state, "superseded")
        self.assertEqual(set(old.line_ids.team_id.ids), set(teams.ids))
        self.assertEqual(set(new.line_ids.team_id.ids), set((teams[:1] | replacement).ids))

    def test_amendment_requires_reason_and_current_snapshot(self):
        teams, entries = self._approved()
        self.window.action_finalize()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.window.amend_finalized_teams(teams.ids, "", self.window.participant_set_id.id)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.window.amend_finalized_teams(teams.ids, "Reviewed", 0)

    def test_managed_participant_cannot_be_confirmed_independently(self):
        teams, entries = self._approved()
        self.window.action_finalize()
        participant = self.env["federation.tournament.participant"].search([
            ("source_entry_id", "=", entries[0].id),
        ], limit=1)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            participant.write({"state": "withdrawn"})

    def test_another_window_cannot_overwrite_finalized_division(self):
        teams, entries = self._approved()
        self.window.action_finalize()
        other = self.env["federation.registration.window"].create({
            "name": "Conflicting window", "edition_id": self.edition.id,
            "division_id": self.division.id, "state": "closed",
        })
        self.env["federation.competition.entry"].create([
            {"window_id": other.id, "team_id": team.id, "state": "approved"}
            for team in teams
        ])
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            other.action_finalize()
