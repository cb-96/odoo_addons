from odoo.tests.common import TransactionCase


class TestCompetitionScheduleScope(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        club = cls.env["federation.club"].create({"name": "Scope Club"})
        cls.teams = cls.env["federation.team"].create(
            [
                {"name": "Scope A", "club_id": club.id},
                {"name": "Scope B", "club_id": club.id},
            ]
        )
        season = cls.env["federation.season"].create(
            {
                "name": "Scope Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Scope Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Scope Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        division = cls.env["federation.tournament"].create(
            {
                "name": "Scope Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )
        participant_set = cls.env["federation.participant.set"].create(
            {
                "name": "Scope Participants",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        cls.env["federation.participant.set.line"].create(
            [
                {
                    "participant_set_id": participant_set.id,
                    "team_id": team.id,
                    "seed": index,
                }
                for index, team in enumerate(cls.teams, 1)
            ]
        )
        cls.structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Scope Format",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "participant_set_id": participant_set.id,
                "format_type": "custom",
                "state": "generated",
            }
        )
        cls.pool_stage, cls.finals_stage = cls.env["federation.structure.stage"].create(
            [
                {
                    "name": "Pool",
                    "structure_id": cls.structure.id,
                    "stage_type": "pool",
                },
                {
                    "name": "Finals",
                    "structure_id": cls.structure.id,
                    "stage_type": "knockout",
                },
            ]
        )
        cls.pool_fixture, cls.finals_fixture = cls.env["federation.fixture"].create(
            [
                {
                    "structure_id": cls.structure.id,
                    "stage_id": cls.pool_stage.id,
                    "round_number": 1,
                    "home_team_id": cls.teams[0].id,
                    "away_team_id": cls.teams[1].id,
                },
                {
                    "structure_id": cls.structure.id,
                    "stage_id": cls.finals_stage.id,
                    "round_number": 1,
                    "home_team_id": cls.teams[1].id,
                    "away_team_id": cls.teams[0].id,
                },
            ]
        )
        venue = cls.env["federation.venue"].create({"name": "Scope Venue"})
        cls.matchday = cls.env["federation.matchday"].create(
            {
                "name": "Scope Day",
                "edition_id": cls.edition.id,
                "date": "2026-10-10",
                "venue_id": venue.id,
            }
        )

    def test_selected_stage_excludes_other_stage_fixtures(self):
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {
                "edition_id": self.edition.id,
                "structure_ids": [(6, 0, self.structure.ids)],
                "stage_ids": [(6, 0, self.pool_stage.ids)],
                "matchday_ids": [(6, 0, self.matchday.ids)],
            }
        )

        included, deferred, excluded = wizard._fixtures()

        self.assertEqual(included, self.pool_fixture)
        self.assertFalse(deferred)
        self.assertEqual(excluded, self.finals_fixture)
