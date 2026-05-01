from odoo.tests.common import TransactionCase


class TestStageProgressionWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Progression Club",
                "code": "PGC",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Progression Season",
                "code": "PGS",
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Belgian Championship Men",
                "code": "BCM",
                "season_id": cls.season.id,
                "date_start": "2025-06-01",
                "state": "in_progress",
                "gender": "male",
            }
        )
        cls.round_robin_stage = cls.env["federation.tournament.stage"].create(
            {
                "name": "Round Robin",
                "tournament_id": cls.tournament.id,
                "stage_type": "group",
            }
        )
        cls.knockout_stage = cls.env["federation.tournament.stage"].create(
            {
                "name": "Knockout",
                "tournament_id": cls.tournament.id,
                "sequence": 20,
                "stage_type": "knockout",
            }
        )

        cls.teams = cls.env["federation.team"]
        cls.participants = cls.env["federation.tournament.participant"]
        for index in range(1, 5):
            team = cls.env["federation.team"].create(
                {
                    "name": f"Progression Team {index}",
                    "club_id": cls.club.id,
                    "code": f"PGT{index}",
                    "gender": "male",
                }
            )
            cls.teams |= team
            cls.participants |= cls.env["federation.tournament.participant"].create(
                {
                    "tournament_id": cls.tournament.id,
                    "team_id": team.id,
                    "stage_id": cls.round_robin_stage.id,
                    "state": "confirmed",
                    "seed": index,
                }
            )

        cls.progression = cls.env["federation.stage.progression"].create(
            {
                "tournament_id": cls.tournament.id,
                "source_stage_id": cls.round_robin_stage.id,
                "target_stage_id": cls.knockout_stage.id,
                "rank_from": 1,
                "rank_to": 2,
                "seeding_method": "keep_rank",
                "auto_advance": True,
            }
        )
        cls.round_robin_group = cls.env["federation.tournament.group"].create(
            {
                "name": "Round Robin Group A",
                "stage_id": cls.round_robin_stage.id,
            }
        )

    def _create_done_match(self, home_team, away_team, home_score, away_score):
        """Exercise create done match."""
        values = {
            "tournament_id": self.tournament.id,
            "stage_id": self.round_robin_stage.id,
            "home_team_id": home_team.id,
            "away_team_id": away_team.id,
            "home_score": home_score,
            "away_score": away_score,
            "state": "done",
        }
        if "include_in_official_standings" in self.env["federation.match"]._fields:
            values["include_in_official_standings"] = True
        return self.env["federation.match"].create(values)

    def test_freezing_round_robin_standing_auto_advances_top_two(self):
        """Test that freezing round robin standing auto advances top two."""
        self._create_done_match(self.teams[0], self.teams[1], 3, 0)
        self._create_done_match(self.teams[0], self.teams[2], 2, 0)
        self._create_done_match(self.teams[0], self.teams[3], 1, 0)
        self._create_done_match(self.teams[1], self.teams[2], 2, 0)
        self._create_done_match(self.teams[1], self.teams[3], 4, 1)
        self._create_done_match(self.teams[2], self.teams[3], 2, 1)

        standing = self.env["federation.standing"].create(
            {
                "name": "Round Robin Standing",
                "tournament_id": self.tournament.id,
                "stage_id": self.round_robin_stage.id,
            }
        )

        standing.action_recompute()
        standing.action_freeze()

        advanced = self.env["federation.tournament.participant"].search(
            [
                ("tournament_id", "=", self.tournament.id),
                ("stage_id", "=", self.knockout_stage.id),
            ],
            order="seed asc, id asc",
        )

        self.assertEqual(len(advanced), 2)
        self.assertEqual(advanced.mapped("team_id"), self.teams[:2])
        self.assertEqual(advanced.mapped("seed"), [1, 2])
        self.assertEqual(set(advanced.mapped("state")), {"confirmed"})
        self.assertEqual(self.progression.state, "executed")

    def test_execute_clears_source_group_when_target_group_is_empty(self):
        """Advancing into a stage without target groups should clear the old group."""
        self.participants.write({"group_id": self.round_robin_group.id})

        standing = self.env["federation.standing"].create(
            {
                "name": "Group A Standing",
                "tournament_id": self.tournament.id,
                "stage_id": self.round_robin_stage.id,
                "group_id": self.round_robin_group.id,
                "state": "frozen",
            }
        )
        self.env["federation.standing.line"].create(
            [
                {
                    "standing_id": standing.id,
                    "participant_id": self.participants[0].id,
                    "rank": 1,
                    "points": 9,
                    "score_for": 6,
                    "score_against": 1,
                },
                {
                    "standing_id": standing.id,
                    "participant_id": self.participants[1].id,
                    "rank": 2,
                    "points": 6,
                    "score_for": 4,
                    "score_against": 2,
                },
            ]
        )

        progression = self.env["federation.stage.progression"].create(
            {
                "tournament_id": self.tournament.id,
                "source_stage_id": self.round_robin_stage.id,
                "source_group_id": self.round_robin_group.id,
                "target_stage_id": self.knockout_stage.id,
                "rank_from": 1,
                "rank_to": 2,
                "seeding_method": "keep_rank",
            }
        )

        progression.action_execute()

        advanced = self.env["federation.tournament.participant"].search(
            [
                ("tournament_id", "=", self.tournament.id),
                ("stage_id", "=", self.knockout_stage.id),
            ],
            order="seed asc, id asc",
        )

        self.assertEqual(len(advanced), 2)
        self.assertEqual(advanced.mapped("team_id"), self.teams[:2])
        self.assertFalse(advanced.mapped("group_id"))
