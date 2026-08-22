from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_stage_graph")
class TestStageGraphEngine(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        club = cls.env["federation.club"].create({"name": "Graph Club"})
        cls.teams = cls.env["federation.team"]
        for i in range(1, 6):
            cls.teams |= cls.env["federation.team"].create(
                {"name": f"Graph Team {i}", "club_id": club.id}
            )
        season = cls.env["federation.season"].create(
            {
                "name": "Graph 26-27",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Graph League", "competition_type": "league"}
        )
        edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Graph Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        division = cls.env["federation.tournament"].create(
            {
                "name": "Graph Division",
                "edition_id": edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )
        pset = cls.env["federation.participant.set"].create(
            {
                "name": "Graph Participants",
                "edition_id": edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        cls.env["federation.participant.set.line"].create(
            [
                {"participant_set_id": pset.id, "team_id": team.id, "seed": i}
                for i, team in enumerate(cls.teams, 1)
            ]
        )
        cls.structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Graph",
                "edition_id": edition.id,
                "division_id": division.id,
                "participant_set_id": pset.id,
                "format_type": "custom",
            }
        )

    def test_five_team_full_placement_bracket_generates_classification(self):
        stage = self.env["federation.structure.stage"].create(
            {
                "name": "Placement",
                "structure_id": self.structure.id,
                "stage_type": "placement",
                "format_type": "placement_bracket",
                "source_type": "registration",
            }
        )
        stage.action_prepare_stage()
        self.assertEqual(len(stage.stage_participant_ids), 5)
        self.assertTrue(stage.stage_fixture_ids)
        ranges = {
            (f.placement_from, f.placement_to)
            for f in stage.stage_fixture_ids
            if f.placement_from
        }
        self.assertIn((1, 2), ranges)

    def test_cycle_is_rejected(self):
        a = self.env["federation.structure.stage"].create(
            {
                "name": "A",
                "structure_id": self.structure.id,
                "stage_type": "league",
                "format_type": "single_round_robin",
                "source_type": "progression",
            }
        )
        b = self.env["federation.structure.stage"].create(
            {
                "name": "B",
                "structure_id": self.structure.id,
                "stage_type": "league",
                "format_type": "single_round_robin",
                "source_type": "progression",
            }
        )
        self.env["federation.stage.progression"].create(
            {
                "name": "A-B",
                "source_stage_id": a.id,
                "target_stage_id": b.id,
                "rank_from": 1,
                "rank_to": 2,
            }
        )
        self.env["federation.stage.progression"].create(
            {
                "name": "B-A",
                "source_stage_id": b.id,
                "target_stage_id": a.id,
                "rank_from": 1,
                "rank_to": 2,
            }
        )
        with self.assertRaises(ValidationError):
            self.env["federation.stage.graph.engine"].validate_graph(self.structure)
