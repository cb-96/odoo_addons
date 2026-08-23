from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_fixture_result_ownership")
class TestFixtureResultOwnership(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        club = cls.env["federation.club"].create({"name": "Ownership Club"})
        cls.teams = cls.env["federation.team"].create(
            [
                {"name": "Ownership A", "club_id": club.id},
                {"name": "Ownership B", "club_id": club.id},
                {"name": "Ownership C", "club_id": club.id},
            ]
        )
        season = cls.env["federation.season"].create(
            {
                "name": "Ownership Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Ownership Competition", "competition_type": "league"}
        )
        edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Ownership Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        cls.division = cls.env["federation.tournament"].create(
            {
                "name": "Ownership Division",
                "edition_id": edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )
        participant_set = cls.env["federation.participant.set"].create(
            {
                "name": "Ownership Participants",
                "edition_id": edition.id,
                "division_id": cls.division.id,
                "state": "finalized",
            }
        )
        cls.env["federation.participant.set.line"].create(
            [
                {
                    "participant_set_id": participant_set.id,
                    "team_id": team.id,
                    "seed": seed,
                }
                for seed, team in enumerate(cls.teams, 1)
            ]
        )
        cls.structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Ownership Structure",
                "edition_id": edition.id,
                "division_id": cls.division.id,
                "participant_set_id": participant_set.id,
                "format_type": "custom",
            }
        )

    def _stage(self, format_type="single_round_robin", stage_type="league"):
        return self.env["federation.structure.stage"].create(
            {
                "name": "Ownership Stage",
                "structure_id": self.structure.id,
                "stage_type": stage_type,
                "format_type": format_type,
                "source_type": "registration",
            }
        )

    def test_playable_fixture_materializes_exactly_one_match(self):
        stage = self._stage()
        stage.action_prepare_stage()
        fixture = stage.stage_fixture_ids[0]
        self.assertTrue(fixture.operational_match_id)
        self.assertEqual(fixture.operational_match_id.logical_fixture_id, fixture)
        self.assertEqual(fixture.operational_match_id.tournament_id, self.division)
        first = fixture.operational_match_id
        second = fixture.action_materialize_match()
        self.assertEqual(second, first)
        self.assertEqual(
            self.env["federation.match"].search_count(
                [("logical_fixture_id", "=", fixture.id)]
            ),
            1,
        )

    def test_unresolved_fixture_cannot_materialize(self):
        stage = self._stage("knockout", "knockout")
        fixture = self.env["federation.fixture"].create(
            {
                "structure_id": self.structure.id,
                "stage_id": stage.id,
                "round_number": 2,
                "home_team_id": self.teams[0].id,
                "state": "pending",
            }
        )
        with self.assertRaises(ValidationError):
            fixture.action_materialize_match()

    def test_bye_is_structural_and_has_no_fake_result(self):
        stage = self._stage("knockout", "knockout")
        stage.action_prepare_stage()
        byes = stage.stage_fixture_ids.filtered("bye_team_id")
        self.assertTrue(byes)
        self.assertFalse(byes.mapped("operational_match_id"))
        self.assertTrue(all(fixture.state == "completed" for fixture in byes))

    def test_fixture_result_is_read_only_and_match_approval_completes_fixture(self):
        stage = self._stage()
        stage.action_prepare_stage()
        fixture = stage.stage_fixture_ids[0]
        match = fixture.operational_match_id.sudo()
        match.write({"home_score": 2, "away_score": 1, "result_state": "verified"})
        match.action_approve_result()
        self.assertEqual(fixture.state, "completed")
        self.assertEqual(fixture.result_state, "approved")
        self.assertEqual(fixture.home_score, 2)
        with self.assertRaises(ValidationError):
            fixture.action_approve_result()

    def test_contest_invalidates_unprogressed_snapshot(self):
        stage = self._stage()
        stage.action_prepare_stage()
        for fixture in stage.stage_fixture_ids:
            fixture.operational_match_id.sudo().write(
                {
                    "home_score": 1,
                    "away_score": 0,
                    "result_state": "approved",
                    "include_in_official_standings": True,
                }
            )
            fixture.operational_match_id._sync_logical_fixture_result()
        stage.action_freeze_standings()
        match = stage.stage_fixture_ids[0].operational_match_id.sudo()
        match.result_contest_reason = "Score sheet review"
        match.action_contest_result()
        self.assertFalse(stage.standing_snapshot_id)
        self.assertEqual(stage.graph_state, "active")
        self.assertEqual(stage.stage_fixture_ids[0].state, "ready")
