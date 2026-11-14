from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase

from odoo.addons.sports_federation_registration.models.participant_handoff import (
    governed,
)


class TestRegistrationTeamSelection(TransactionCase):
    """Tests for the registration desk team selection rules."""

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

    def test_available_teams_exclude_registered_and_mismatched_teams(self):
        eligible_team = self._make_team("Eligible Team")
        registered_team = self._make_team("Registered Team")
        wrong_gender_team = self._make_team("Wrong Gender Team", gender="female")
        wrong_category_team = self._make_team("Wrong Category Team", category="junior")
        self.env["federation.competition.entry"].create(
            {
                "window_id": self.window.id,
                "team_id": registered_team.id,
            }
        )

        entry = self.env["federation.competition.entry"].new(
            {"window_id": self.window.id}
        )
        entry._compute_available_team_ids()

        available_team_ids = entry.available_team_ids._origin.ids
        self.assertIn(eligible_team.id, available_team_ids)
        self.assertNotIn(registered_team.id, available_team_ids)
        self.assertNotIn(wrong_gender_team.id, available_team_ids)
        self.assertNotIn(wrong_category_team.id, available_team_ids)

    def test_invalid_gender_and_category_are_rejected_server_side(self):
        for name, category, gender in (
            ("Invalid Gender Team", "senior", "female"),
            ("Invalid Category Team", "junior", "male"),
        ):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    self.env["federation.competition.entry"].create(
                        {
                            "window_id": self.window.id,
                            "team_id": self._make_team(
                                name, category=category, gender=gender
                            ).id,
                        }
                    )

    def test_onchange_returns_available_team_domain(self):
        eligible_team = self._make_team("Onchange Eligible Team")
        registered_team = self._make_team("Onchange Registered Team")
        self.env["federation.competition.entry"].create(
            {
                "window_id": self.window.id,
                "team_id": registered_team.id,
            }
        )

        entry = self.env["federation.competition.entry"].new(
            {"window_id": self.window.id}
        )
        result = entry._onchange_window_id()

        self.assertEqual(
            result["domain"]["team_id"],
            [("id", "in", entry.available_team_ids.ids)],
        )
        self.assertIn(eligible_team.id, entry.available_team_ids.ids)
        self.assertNotIn(registered_team.id, entry.available_team_ids.ids)

    def test_direct_team_picker_materializes_registration_and_participant_snapshot(
        self,
    ):
        first = self._make_team("Direct Team A")
        second = self._make_team("Direct Team B")
        wizard = self.env["federation.competition.team.selection.wizard"].create(
            {
                "edition_id": self.edition.id,
                "division_id": self.division.id,
                "window_id": self.window.id,
                "team_ids": [(6, 0, [first.id, second.id])],
            }
        )

        wizard.action_apply()

        self.assertEqual(self.window.state, "finalized")
        self.assertEqual(set(self.window.entry_ids.mapped("state")), {"approved"})
        self.assertEqual(
            set(self.window.participant_set_id.line_ids.mapped("team_id").ids),
            {first.id, second.id},
        )
        participant_set = self.window.participant_set_id
        self.assertEqual(
            self.window.materialize_direct_team_selection(first | second),
            participant_set,
        )

    # ── participant records follow the finalised team list ───────────────

    def _amend(self, teams):
        """Change a finalized team list the governed way: amend with a reason."""
        return self.window.amend_finalized_teams(
            teams.ids, "Team list changed", self.window.participant_set_id.id
        )

    def _participants(self):
        return self.env["federation.tournament.participant"].search(
            [("tournament_id", "=", self.division.id)]
        )

    def test_finalising_the_team_list_creates_confirmed_participants(self):
        first = self._make_team("Sync Team A")
        second = self._make_team("Sync Team B")

        self.window.materialize_direct_team_selection(first | second)

        participants = self._participants()
        self.assertEqual(participants.mapped("team_id"), first | second)
        self.assertEqual(set(participants.mapped("state")), {"confirmed"})
        self.assertEqual(sorted(participants.mapped("seed")), [1, 2])

    def test_participant_sync_is_idempotent(self):
        first = self._make_team("Idempotent Team A")
        second = self._make_team("Idempotent Team B")
        participant_set = self.window.materialize_direct_team_selection(first | second)

        self.window._sync_tournament_participants(participant_set)
        self.window._sync_tournament_participants(participant_set)

        self.assertEqual(len(self._participants()), 2)

    def test_replacing_the_team_list_withdraws_teams_that_were_taken_out(self):
        first = self._make_team("Replace Team A")
        second = self._make_team("Replace Team B")
        third = self._make_team("Replace Team C")
        self.window.materialize_direct_team_selection(first | second)

        self._amend(second | third)

        state_by_team = {
            participant.team_id: participant.state
            for participant in self._participants()
        }
        self.assertEqual(state_by_team[first], "withdrawn")
        self.assertEqual(state_by_team[second], "confirmed")
        self.assertEqual(state_by_team[third], "confirmed")

    def test_a_team_selected_again_is_confirmed_again(self):
        first = self._make_team("Return Team A")
        second = self._make_team("Return Team B")
        third = self._make_team("Return Team C")
        self.window.materialize_direct_team_selection(first | second)
        self._amend(second | third)

        self._amend(first | second)

        state_by_team = {
            participant.team_id: participant.state
            for participant in self._participants()
        }
        self.assertEqual(state_by_team[first], "confirmed")
        self.assertEqual(state_by_team[third], "withdrawn")

    def test_migration_style_sync_skips_a_team_that_is_no_longer_eligible(self):
        first = self._make_team("Eligible Sync Team")
        second = self._make_team("Later Ineligible Team")
        participant_set = self.window.materialize_direct_team_selection(first | second)
        # Simulate a database from before participants were tracked: detach the
        # managed history (governed), then remove the rows.
        participants = governed(self._participants())
        participants.write(
            {"source_entry_id": False, "source_participant_set_id": False}
        )
        participants.unlink()
        second.write({"gender": "female"})

        self.window._sync_tournament_participants(participant_set, skip_ineligible=True)

        self.assertEqual(self._participants().mapped("team_id"), first)
