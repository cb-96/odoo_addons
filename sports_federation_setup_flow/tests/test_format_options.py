from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.sports_federation_registration.models.participant_handoff import (
    governed,
)


@tagged("post_install", "-at_install", "sf_competition_formats")
class TestFormatOptions(TransactionCase):
    """Guided formats with options, custom stages and stage-aware planning."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {
                "name": "Options 26-27",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Options Cup", "competition_type": "cup"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Options Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        cls.division = cls.env["federation.tournament"].create(
            {
                "name": "Options Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2027-03-01",
            }
        )
        club = cls.env["federation.club"].create({"name": "Options Club"})
        cls.teams = cls.env["federation.team"].create(
            [{"name": "Options Team %s" % i, "club_id": club.id} for i in range(1, 9)]
        )
        cls.participant_set = cls.env["federation.participant.set"].create(
            {
                "name": "Options Participants",
                "edition_id": cls.edition.id,
                "division_id": cls.division.id,
                "state": "finalized",
            }
        )
        governed(cls.env["federation.participant.set.line"]).create(
            [
                {
                    "participant_set_id": cls.participant_set.id,
                    "team_id": team.id,
                    "seed": seed,
                }
                for seed, team in enumerate(cls.teams, 1)
            ]
        )
        venue = cls.env["federation.venue"].create({"name": "Options Venue"})
        cls.courts = cls.env["federation.playing.area"].create(
            [{"name": "Options Court %s" % i, "venue_id": venue.id} for i in (1, 2)]
        )
        cls.days = cls.env["federation.matchday"].create(
            [
                {
                    "name": "Options Day %s" % index,
                    "edition_id": cls.edition.id,
                    "date": "2027-03-%02d" % (index * 7),
                    "venue_id": venue.id,
                    "planning_court_ids": [(6, 0, cls.courts.ids)],
                    "default_day_start_hour": 9.0,
                    "default_day_end_hour": 18.0,
                    "default_slot_duration_minutes": 40,
                }
                for index in (1, 2, 3)
            ]
        )

    def _wizard(self, **values):
        # Defaults come from the context, exactly like the planner opens it.
        return (
            self.env["federation.competition.format.setup.wizard"]
            .with_context(
                default_edition_id=self.edition.id, default_division_id=self.division.id
            )
            .create(
                {
                    "edition_id": self.edition.id,
                    "division_id": self.division.id,
                    "participant_set_id": self.participant_set.id,
                    **values,
                }
            )
        )

    def _structure(self):
        return self.env["federation.competition.structure"].search(
            [("division_id", "=", self.division.id)],
            order="version desc,id desc",
            limit=1,
        )

    def test_preview_outline_and_options(self):
        wizard = self._wizard(
            format_type="pool_knockout", pool_count=2, qualifiers_per_pool=3
        )
        self.assertEqual(wizard.preview_match_count, 6 + 6 + 5)
        self.assertIn("Group A", wizard.preview_outline)
        self.assertIn("Top 3 of every group", wizard.preview_outline)
        wizard.qualifiers_per_pool = 5
        self.assertFalse(wizard.preview_feasible)
        wizard.preview_confirmed = True
        with self.assertRaises(ValidationError):
            wizard.action_apply()

    def test_confirm_generates_every_stage_and_reopens_with_the_choice(self):
        self._wizard(
            format_type="split_pools",
            split_rank=4,
            preview_confirmed=True,
            second_phase_carryover="same_group_results",
        ).action_apply()
        structure = self._structure()
        self.assertEqual(structure.state, "frozen")
        self.assertEqual(len(structure.stage_ids), 3)
        self.assertEqual(len(structure.fixture_ids), 28 + 6 + 6)
        reopened = self._wizard()
        self.assertEqual(reopened.format_type, "split_pools")
        self.assertEqual(reopened.split_rank, 4)
        self.assertEqual(reopened.second_phase_carryover, "same_group_results")
        # Same choice: the frozen structure is reused, not rebuilt.
        reopened.preview_confirmed = True
        reopened.action_apply()
        self.assertEqual(self._structure(), structure)

    def test_knockout_for_every_place_uses_a_placement_bracket(self):
        self._wizard(
            format_type="knockout", knockout_full_placement=True, preview_confirmed=True
        ).action_apply()
        structure = self._structure()
        self.assertEqual(structure.format_type, "placement_bracket")
        self.assertEqual(self._wizard().knockout_full_placement, True)

    def test_custom_opens_the_stage_builder_first(self):
        action = self._wizard(format_type="custom").action_open_stage_builder()
        structure = self._structure()
        self.assertEqual(structure.format_type, "custom")
        self.assertEqual(action["tag"], "federation_stage_builder")
        self.assertEqual(action["params"]["structure_id"], structure.id)
        self.assertEqual(structure.state, "draft")
        self.env["federation.structure.stage"].create(
            {
                "name": "Everyone",
                "structure_id": structure.id,
                "stage_type": "league",
                "format_type": "single_round_robin",
                "source_type": "registration",
            }
        )
        self._wizard(format_type="custom").action_apply()
        self.assertEqual(structure.state, "frozen")
        self.assertEqual(len(structure.fixture_ids), 28)

    def test_planning_keeps_the_knockout_after_the_groups(self):
        self._wizard(
            format_type="pool_knockout",
            pool_count=2,
            qualifiers_per_pool=2,
            preview_confirmed=True,
        ).action_apply()
        structure = self._structure()
        knockout = structure.stage_ids.filtered(
            lambda stage: stage.source_type == "progression"
        )
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {"edition_id": self.edition.id}
        )
        wizard._onchange_edition_id()
        self.assertEqual(len(wizard.stage_window_ids), len(structure.stage_ids))
        window = wizard.stage_window_ids.filtered(
            lambda line: line.stage_id == knockout
        )
        window.matchday_ids = [(6, 0, self.days[2].ids)]
        wizard.action_generate()
        self.assertEqual(knockout.matchday_ids, self.days[2])
        knockout_days = self.days.filtered(
            lambda day: day.allocation_ids.mapped("fixture_ids")
            & knockout.stage_fixture_ids
        )
        self.assertEqual(knockout_days, self.days[2])
        group_fixtures = structure.fixture_ids - knockout.stage_fixture_ids
        self.assertFalse(
            self.days[2].allocation_ids.mapped("fixture_ids") & group_fixtures
        )

    def test_validator_rejects_stage_outside_its_game_days(self):
        self._wizard(format_type="pool_knockout", preview_confirmed=True).action_apply()
        structure = self._structure()
        knockout = structure.stage_ids.filtered(
            lambda stage: stage.source_type == "progression"
        )
        knockout.matchday_ids = [(6, 0, self.days[2].ids)]
        day = self.days[0]
        fixture = knockout.stage_fixture_ids.filtered(
            lambda item: item._is_schedulable()
        )[:1]
        self.env["federation.matchday.allocation"].create(
            {
                "matchday_id": day.id,
                "structure_id": structure.id,
                "manual_only": True,
                "manual_fixture_ids": [(6, 0, fixture.ids)],
            }
        )
        slot = self.env["federation.schedule.slot"].create(
            {
                "matchday_id": day.id,
                "court_id": self.courts[0].id,
                "start_datetime": "2027-03-07 17:00:00",
                "end_datetime": "2027-03-07 17:40:00",
            }
        )
        schedule = self.env["federation.schedule"].create(
            {
                "name": "Options schedule",
                "edition_id": self.edition.id,
                "structure_id": structure.id,
                "matchday_id": day.id,
            }
        )
        result = self.env["federation.schedule.validator"].validate_map(
            schedule, {fixture.id: slot.id}
        )
        self.assertIn("stage_game_day", [error["code"] for error in result["errors"]])
