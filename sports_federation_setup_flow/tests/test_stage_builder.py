from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.sports_federation_registration.models.participant_handoff import (
    governed,
)


@tagged("post_install", "-at_install", "sf_competition_formats")
class TestStageBuilderAndReuse(TransactionCase):
    """Custom stages in the builder, saved templates and next-season reuse."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Builder 26-27",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        cls.next_season = cls.env["federation.season"].create(
            {
                "name": "Builder 27-28",
                "date_start": "2027-09-01",
                "date_end": "2028-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Builder League", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Builder Edition",
                "competition_id": competition.id,
                "season_id": cls.season.id,
                "date_start": "2026-10-03",
                "date_end": "2027-05-29",
            }
        )
        cls.division = cls.env["federation.tournament"].create(
            {
                "name": "Builder Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": cls.season.id,
                "date_start": "2026-10-03",
            }
        )
        club = cls.env["federation.club"].create({"name": "Builder Club"})
        cls.teams = cls.env["federation.team"].create(
            [{"name": "Builder Team %s" % i, "club_id": club.id} for i in range(1, 9)]
        )
        cls.pset = cls._participants(cls.edition, cls.division, cls.teams)
        cls.builder = cls.env["federation.stage.builder"]

    @classmethod
    def _participants(cls, edition, division, teams):
        pset = cls.env["federation.participant.set"].create(
            {
                "name": "Builder Participants",
                "edition_id": edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        governed(cls.env["federation.participant.set.line"]).create(
            [
                {"participant_set_id": pset.id, "team_id": team.id, "seed": seed}
                for seed, team in enumerate(teams, 1)
            ]
        )
        return pset

    def _custom(self):
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
        return action["params"]["structure_id"]

    def _stage(self, data, name):
        return next(stage for stage in data["stages"] if stage["name"] == name)

    def _build_top_four_final(self):
        structure_id = self._custom()
        data = self.builder.add_stage(
            structure_id, {"name": "League", "format_type": "single_round_robin"}
        )
        league = self._stage(data, "League")
        self.assertEqual((league["teams"], league["matches"]), (8, 28))
        data = self.builder.add_stage(
            structure_id,
            {
                "name": "Final four",
                "format_type": "knockout",
                "after_stage_id": league["id"],
                "places": 4,
            },
        )
        final = self._stage(data, "Final four")
        self.assertEqual((final["column"], final["teams"], final["matches"]), (1, 4, 3))
        self.assertIn("Places 1–4 of League → Final four", data["links"][0]["sentence"])
        self.assertFalse(data["issues"])
        return structure_id, data

    def test_build_check_and_generate(self):
        structure_id, data = self._build_top_four_final()
        league = self._stage(data, "League")
        final = self._stage(data, "Final four")
        # A place that does not exist is reported on the link.
        data = self.builder.add_link(
            structure_id,
            {
                "source_id": league["id"],
                "target_id": final["id"],
                "rank_from": 9,
                "rank_to": 10,
            },
        )
        self.assertTrue(
            any(
                "place 10 does not exist" in issue["message"]
                for issue in data["issues"]
            )
        )
        with self.assertRaises(ValidationError):
            self.builder.generate(structure_id)
        bad = next(link for link in data["links"] if link["rank_from"] == 9)
        data = self.builder.delete_link(structure_id, bad["id"])
        self.assertFalse(data["issues"])
        # Links cannot point backwards.
        with self.assertRaises(ValidationError):
            self.builder.add_link(
                structure_id,
                {
                    "source_id": final["id"],
                    "target_id": league["id"],
                    "rank_from": 1,
                    "rank_to": 2,
                },
            )
        self.builder.update_stage(
            structure_id, final["id"], {"carryover_policy": "full_points"}
        )
        self.builder.generate(structure_id)
        structure = self.env["federation.competition.structure"].browse(structure_id)
        self.assertEqual(structure.state, "frozen")
        self.assertEqual(
            len(structure.fixture_ids.filtered(lambda f: not f.bye_team_id)), 28 + 3
        )
        data = self.builder.load(structure_id)
        self.assertFalse(data["structure"]["editable"])
        self.assertTrue(data["structure"]["can_new_version"])
        draft = self.builder.new_version(structure_id)
        self.assertTrue(draft["structure"]["editable"])
        self.assertEqual(
            [stage["name"] for stage in draft["stages"]], ["League", "Final four"]
        )
        self.assertEqual(len(draft["links"]), 1)

    def test_template_round_trip(self):
        structure_id, _data = self._build_top_four_final()
        template = self.builder.save_template(structure_id, "League and final four")
        template = self.env["federation.competition.format.template"].browse(
            template["id"]
        )
        self.assertEqual(template.format_type, "custom")
        self.assertIn("League → Final four", template.stage_summary)
        other = self.env["federation.tournament"].create(
            {
                "name": "Builder Second Division",
                "edition_id": self.edition.id,
                "competition_id": self.edition.competition_id.id,
                "season_id": self.season.id,
                "date_start": "2026-10-03",
            }
        )
        pset = self._participants(self.edition, other, self.teams)
        wizard = (
            self.env["federation.competition.format.setup.wizard"]
            .with_context(
                default_edition_id=self.edition.id, default_division_id=other.id
            )
            .create({"participant_set_id": pset.id})
        )
        wizard.template_id = template
        wizard._onchange_template_id()
        self.assertEqual(wizard.format_type, "custom")
        action = wizard.action_apply()
        copied = self.env["federation.competition.structure"].browse(
            action["params"]["structure_id"]
        )
        self.assertEqual(copied.template_id, template)
        self.assertEqual(copied.stage_ids.mapped("name"), ["League", "Final four"])
        self.assertEqual(copied.stage_ids[1].incoming_progression_ids.rank_to, 4)

    def test_guided_template_fills_options(self):
        self.env["federation.competition.format.setup.wizard"].create(
            {
                "edition_id": self.edition.id,
                "division_id": self.division.id,
                "participant_set_id": self.pset.id,
                "format_type": "pool_knockout",
                "pool_count": 2,
                "qualifiers_per_pool": 3,
                "preview_confirmed": True,
            }
        ).action_apply()
        structure = self.env["federation.competition.structure"].search(
            [("division_id", "=", self.division.id)], order="version desc", limit=1
        )
        template = structure.action_save_as_template("Groups top three")
        wizard = self.env["federation.competition.format.setup.wizard"].create(
            {
                "edition_id": self.edition.id,
                "division_id": self.division.id,
                "participant_set_id": self.pset.id,
                "format_type": "single_round_robin",
            }
        )
        wizard.template_id = template
        wizard._onchange_template_id()
        self.assertEqual(
            (wizard.format_type, wizard.qualifiers_per_pool), ("pool_knockout", 3)
        )

    def test_copy_to_next_season_reuses_format_and_game_days(self):
        self.env["federation.competition.format.setup.wizard"].create(
            {
                "edition_id": self.edition.id,
                "division_id": self.division.id,
                "participant_set_id": self.pset.id,
                "format_type": "split_pools",
                "split_rank": 4,
                "preview_confirmed": True,
            }
        ).action_apply()
        venue = self.env["federation.venue"].create({"name": "Builder Venue"})
        day = self.env["federation.matchday"].create(
            {
                "name": "Builder Saturday",
                "edition_id": self.edition.id,
                "date": "2026-10-03",
                "venue_id": venue.id,
            }
        )
        if "division_ids" in day._fields:
            day.division_ids = self.division
        action = (
            self.env["federation.competition.clone.setup.wizard"]
            .create(
                {
                    "source_edition_id": self.edition.id,
                    "name": "Builder Edition next",
                    "season_id": self.next_season.id,
                    "date_start": "2027-10-03",
                    "date_end": "2028-05-29",
                }
            )
            .action_copy_setup()
        )
        copied = self.env["federation.competition.edition"].browse(action["res_id"])
        new_division = copied.tournament_ids
        self.assertEqual(
            new_division.format_source_structure_id.format_type, "split_pools"
        )
        new_day = self.env["federation.matchday"].search(
            [("edition_id", "=", copied.id)]
        )
        self.assertEqual(new_day.date.weekday(), day.date.weekday())
        if "division_ids" in new_day._fields:
            self.assertEqual(new_day.division_ids, new_division)
        pset = self._participants(copied, new_division, self.teams[:6])
        wizard = (
            self.env["federation.competition.format.setup.wizard"]
            .with_context(
                default_edition_id=copied.id, default_division_id=new_division.id
            )
            .create({"participant_set_id": pset.id})
        )
        self.assertEqual(wizard.format_type, "split_pools")
        self.assertEqual(wizard.split_rank, 4)
        self.assertTrue(wizard.source_structure_id)
