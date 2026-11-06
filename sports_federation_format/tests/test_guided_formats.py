from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_competition_formats")
class TestGuidedFormats(TransactionCase):
    """Every match of a multi-stage format exists right after generation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        club = cls.env["federation.club"].create({"name": "Format Club"})
        cls.teams = cls.env["federation.team"].create(
            [{"name": "Format Team %s" % i, "club_id": club.id} for i in range(1, 11)]
        )
        season = cls.env["federation.season"].create(
            {
                "name": "Format 26-27",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Format League", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Format Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        cls.division = cls.env["federation.tournament"].create(
            {
                "name": "Format Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )

    def _structure(self, team_count, **values):
        pset = self.env["federation.participant.set"].create(
            {
                "name": "Format Participants %s" % team_count,
                "edition_id": self.edition.id,
                "division_id": self.division.id,
                "state": "finalized",
            }
        )
        self.env["federation.participant.set.line"].create(
            [
                {"participant_set_id": pset.id, "team_id": team.id, "seed": seed}
                for seed, team in enumerate(self.teams[:team_count], 1)
            ]
        )
        latest = self.env["federation.competition.structure"].search(
            [("division_id", "=", self.division.id)], order="version desc", limit=1
        )
        return self.env["federation.competition.structure"].create(
            {
                "name": "Format",
                "edition_id": self.edition.id,
                "division_id": self.division.id,
                "participant_set_id": pset.id,
                "version": (latest.version + 1) if latest else 1,
                **values,
            }
        )

    def test_groups_with_three_qualifiers_and_cross_seeding(self):
        structure = self._structure(
            8, format_type="pool_knockout", pool_count=2, qualifiers_per_pool=3
        )
        structure.action_generate()
        groups = structure.stage_ids.filtered(lambda stage: stage.stage_type == "pool")
        knockout = structure.stage_ids - groups
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(knockout.incoming_progression_ids), 6)
        self.assertEqual(
            sorted(knockout.incoming_progression_ids.mapped("target_seed_from")),
            [1, 2, 3, 4, 5, 6],
        )
        # Group winners take seeds 1 and 2.
        winners = knockout.incoming_progression_ids.filtered(
            lambda edge: edge.rank_from == 1
        )
        self.assertEqual(sorted(winners.mapped("target_seed_from")), [1, 2])
        playable = structure.fixture_ids.filtered(
            lambda fixture: fixture._is_schedulable()
        )
        self.assertEqual(len(playable), structure.estimated_fixture_count)
        self.assertTrue(
            any("Group" in name for name in knockout.stage_fixture_ids.mapped("name"))
        )

    def test_split_season_creates_placeholder_round_robins(self):
        structure = self._structure(
            10,
            format_type="split_pools",
            split_rank=6,
            second_phase_carryover="full_points",
        )
        structure.action_generate()
        season, top, bottom = structure.stage_ids.sorted("sequence")
        self.assertEqual(len(season.stage_fixture_ids), 45)
        self.assertEqual(len(top.stage_fixture_ids), 15)
        self.assertEqual(len(bottom.stage_fixture_ids), 6)
        self.assertEqual(top.carryover_policy, "full_points")
        self.assertEqual((bottom.final_rank_from, bottom.final_rank_to), (7, 10))
        self.assertTrue(
            all(fixture._is_schedulable() for fixture in top.stage_fixture_ids)
        )
        self.assertIn("#1", " ".join(top.stage_fixture_ids.mapped("name")))
        self.assertEqual(top.graph_state, "waiting")
        self.assertEqual(structure.estimated_fixture_count, 66)

    def test_season_in_two_halves(self):
        structure = self._structure(6, format_type="split_pools", split_rank=6)
        structure.action_generate()
        self.assertEqual(len(structure.stage_ids), 2)
        self.assertEqual(len(structure.fixture_ids), 15 + 15)

    def test_split_rank_leaving_one_team_is_rejected(self):
        structure = self._structure(8, format_type="split_pools", split_rank=7)
        with self.assertRaises(ValidationError):
            structure.action_generate()

    def test_planning_order_puts_earlier_stages_first(self):
        structure = self._structure(8, format_type="pool_knockout", pool_count=2)
        structure.action_generate()
        ordered = structure.fixture_ids._planning_sorted()
        depths = structure.stage_ids._planning_depths()
        values = [depths[fixture.stage_id.id] for fixture in ordered]
        self.assertEqual(values, sorted(values))
