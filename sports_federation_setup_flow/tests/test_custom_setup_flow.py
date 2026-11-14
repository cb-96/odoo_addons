from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.sports_federation_registration.models.participant_handoff import (
    governed,
)


@tagged("post_install", "-at_install", "sf_competition_formats")
class TestCustomFormatSetupFlow(TransactionCase):
    """Custom formats through the guided setup, up to planning."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {
                "name": "Custom 26-27",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Custom Cup", "competition_type": "cup"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Custom Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        cls.division = cls.env["federation.tournament"].create(
            {
                "name": "Custom Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2027-03-01",
            }
        )
        club = cls.env["federation.club"].create({"name": "Custom Club"})
        cls.teams = cls.env["federation.team"].create(
            [{"name": "Custom Team %s" % i, "club_id": club.id} for i in range(1, 7)]
        )
        cls.pset = cls.env["federation.participant.set"].create(
            {
                "name": "Custom Participants",
                "edition_id": cls.edition.id,
                "division_id": cls.division.id,
                "state": "finalized",
            }
        )
        governed(cls.env["federation.participant.set.line"]).create(
            [
                {"participant_set_id": cls.pset.id, "team_id": team.id, "seed": seed}
                for seed, team in enumerate(cls.teams, 1)
            ]
        )
        cls.env["federation.registration.window"].create(
            {
                "name": "Custom Registration",
                "edition_id": cls.edition.id,
                "division_id": cls.division.id,
                "state": "finalized",
                "participant_set_id": cls.pset.id,
            }
        )
        # The window above is finalized directly, so give the division the
        # participants finalizing would create. A finalized division only
        # accepts teams through the amendment command, which the stage engine
        # must not bypass.
        governed(cls.env["federation.tournament.participant"]).create(
            [
                {
                    "tournament_id": cls.division.id,
                    "team_id": team.id,
                    "state": "confirmed",
                }
                for team in cls.teams
            ]
        )
        venue = cls.env["federation.venue"].create({"name": "Custom Venue"})
        court = cls.env["federation.playing.area"].create(
            [{"name": "Custom Court %s" % i, "venue_id": venue.id} for i in (1, 2)]
        )
        cls.days = cls.env["federation.matchday"].create(
            [
                {
                    "name": "Custom Day %s" % index,
                    "edition_id": cls.edition.id,
                    "date": "2027-03-%02d" % (index * 7),
                    "venue_id": venue.id,
                    "planning_court_ids": [(6, 0, court.ids)],
                    "default_day_start_hour": 9.0,
                    "default_day_end_hour": 18.0,
                    "default_slot_duration_minutes": 40,
                }
                for index in (1, 2)
            ]
        )
        cls.builder = cls.env["federation.stage.builder"]

    def _custom_structure(self, with_stage=True):
        action = (
            self.env["federation.competition.format.setup.wizard"]
            .create(
                {
                    "edition_id": self.edition.id,
                    "division_id": self.division.id,
                    "participant_set_id": self.pset.id,
                    "format_type": "custom",
                }
            )
            .action_open_stage_builder()
        )
        structure_id = action["params"]["structure_id"]
        if with_stage:
            self.builder.add_stage(
                structure_id, {"name": "League", "format_type": "single_round_robin"}
            )
        return self.env["federation.competition.structure"].browse(structure_id)

    def test_teams_and_format_keeps_a_custom_draft(self):
        structure = self._custom_structure()
        wizard = (
            self.env["federation.competition.division.setup.wizard"]
            .with_context(default_edition_id=self.edition.id)
            .create({"edition_id": self.edition.id})
        )
        line = wizard.line_ids.filtered(lambda item: item.division_id == self.division)
        self.assertEqual(line.format_type, "custom")
        action = wizard.action_apply()
        # Saving opens the stage builder instead of generating a league.
        self.assertEqual(action["tag"], "federation_stage_builder")
        latest = self.env["federation.competition.structure"].search(
            [("division_id", "=", self.division.id)],
            order="version desc,id desc",
            limit=1,
        )
        self.assertEqual(latest, structure)
        self.assertEqual(latest.state, "draft")

    def test_planner_points_custom_drafts_to_the_stage_builder(self):
        self._custom_structure()
        planner = self.edition.get_competition_planner_data()
        key = "division-%s-stages" % self.division.id
        self.assertIn(key, [issue["key"] for issue in planner["issues"]])
        row = next(row for row in planner["divisions"] if row["id"] == self.division.id)
        self.assertIn("not generated", row["format_name"])
        action = self.edition.action_open_planner_issue(key)
        self.assertEqual(action["tag"], "federation_stage_builder")

    def test_preparing_again_keeps_existing_matches(self):
        structure = self._custom_structure()
        stage = structure.stage_ids
        stage.action_prepare_stage()
        fixtures = stage.stage_fixture_ids
        self.assertTrue(fixtures.filtered("operational_match_id"))
        # Planning generates the draft: the prepared matches are kept.
        structure.action_generate()
        self.assertEqual(stage.stage_fixture_ids, fixtures)
        self.assertEqual(structure.state, "generated")

    def test_planning_a_prepared_custom_draft(self):
        structure = self._custom_structure()
        structure.stage_ids.action_prepare_stage()
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {"edition_id": self.edition.id}
        )
        wizard._onchange_edition_id()
        wizard.structure_ids = structure
        wizard.matchday_ids = self.days
        wizard.action_generate()
        self.assertEqual(structure.state, "frozen")
        planned = self.days.mapped("allocation_ids.fixture_ids")
        self.assertEqual(
            planned, structure.fixture_ids.filtered(lambda f: not f.bye_team_id)
        )

    def test_planning_refuses_unfinished_custom_stages(self):
        structure = self._custom_structure(with_stage=False)
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {"edition_id": self.edition.id}
        )
        wizard.structure_ids = structure
        wizard.matchday_ids = self.days
        wizard.action_generate()
        self.assertTrue(wizard.blocking_issue_count)
        self.assertTrue(
            any(
                "stage builder" in str(item)
                for item in wizard.feasibility_report.get("errors", [])
            )
        )
        self.assertFalse(structure.fixture_ids)
        with self.assertRaisesRegex(ValidationError, "stage builder"):
            wizard._prepare_structures()

    def test_generated_but_unconfirmed_format_is_confirmed_in_the_builder(self):
        structure = self._custom_structure()
        structure.action_generate()
        data = self.builder.load(structure.id)
        self.assertTrue(data["structure"]["can_confirm"])
        self.builder.generate(structure.id)
        self.assertEqual(structure.state, "frozen")

    def test_matches_are_spread_within_the_rest(self):
        """6 teams home & away: 10 matches each over two days of 9:00-18:00."""
        structure = self._custom_structure(with_stage=False)
        self.builder.add_stage(
            structure.id, {"name": "League", "format_type": "double_round_robin"}
        )
        self.builder.generate(structure.id)
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {"edition_id": self.edition.id}
        )
        wizard._onchange_edition_id()
        wizard.action_generate()
        for day in self.days:
            counts = {}
            for fixture in day.allocation_ids.mapped("fixture_ids"):
                for team in fixture.home_team_id | fixture.away_team_id:
                    counts[team] = counts.get(team, 0) + 1
            self.assertEqual(max(counts.values()), 5)
