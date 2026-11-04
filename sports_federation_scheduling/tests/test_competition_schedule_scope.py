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

    def test_waiting_seeded_bracket_is_selected_for_initial_schedule(self):
        self.finals_stage.write(
            {
                "graph_state": "waiting",
                "source_type": "progression",
                "format_type": "knockout",
            }
        )
        self.finals_fixture.write(
            {
                "home_team_id": False,
                "away_team_id": False,
                "home_source_seed": 1,
                "away_source_seed": 2,
            }
        )
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {"edition_id": self.edition.id}
        )
        wizard._onchange_edition_id()

        self.assertIn(self.finals_stage, wizard.stage_ids)
        self.assertIn(self.finals_fixture, wizard._fixtures()[0])

    def test_generated_day_allocations_contain_only_the_distributed_fixtures(self):
        second_day = self.env["federation.matchday"].create(
            {
                "name": "Scope Second Day",
                "edition_id": self.edition.id,
                "date": "2026-10-17",
                "venue_id": self.matchday.venue_id.id,
            }
        )
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {
                "edition_id": self.edition.id,
                "structure_ids": [(6, 0, self.structure.ids)],
                "matchday_ids": [(6, 0, (self.matchday | second_day).ids)],
            }
        )

        wizard._create_allocations(self.matchday, self.pool_fixture)
        wizard._create_allocations(second_day, self.finals_fixture)
        first_schedule = self.env["federation.schedule"].create(
            {
                "name": "Scope First Schedule",
                "edition_id": self.edition.id,
                "structure_id": self.structure.id,
                "matchday_id": self.matchday.id,
            }
        )
        second_schedule = self.env["federation.schedule"].create(
            {
                "name": "Scope Second Schedule",
                "edition_id": self.edition.id,
                "structure_id": self.structure.id,
                "matchday_id": second_day.id,
            }
        )

        self.assertEqual(first_schedule.available_fixture_ids, self.pool_fixture)
        self.assertEqual(second_schedule.available_fixture_ids, self.finals_fixture)

    def test_fixture_allocated_on_another_day_is_not_replanned(self):
        second_day = self.env["federation.matchday"].create(
            {
                "name": "Scope Second Day",
                "edition_id": self.edition.id,
                "date": "2026-10-17",
                "venue_id": self.matchday.venue_id.id,
            }
        )
        self.env["federation.matchday.allocation"].create(
            {
                "matchday_id": self.matchday.id,
                "structure_id": self.structure.id,
                "manual_fixture_ids": [(6, 0, self.pool_fixture.ids)],
                "manual_only": True,
            }
        )
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {
                "edition_id": self.edition.id,
                "structure_ids": [(6, 0, self.structure.ids)],
                "stage_ids": [(6, 0, self.pool_stage.ids)],
                "matchday_ids": [(6, 0, second_day.ids)],
            }
        )

        included, deferred, excluded = wizard._fixtures()

        self.assertFalse(included)
        self.assertFalse(deferred)
        self.assertIn(self.pool_fixture, excluded)

    def test_preview_blocks_a_fixture_allocated_to_multiple_days(self):
        second_day = self.env["federation.matchday"].create(
            {
                "name": "Scope Second Day",
                "edition_id": self.edition.id,
                "date": "2026-10-17",
                "venue_id": self.matchday.venue_id.id,
            }
        )
        for day in (self.matchday, second_day):
            self.env["federation.matchday.allocation"].create(
                {
                    "matchday_id": day.id,
                    "structure_id": self.structure.id,
                    "manual_fixture_ids": [(6, 0, self.pool_fixture.ids)],
                    "manual_only": True,
                }
            )
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {
                "edition_id": self.edition.id,
                "structure_ids": [(6, 0, self.structure.ids)],
                "stage_ids": [(6, 0, self.pool_stage.ids)],
                "matchday_ids": [(6, 0, (self.matchday | second_day).ids)],
            }
        )

        errors, _warnings = wizard._validate_scope()

        self.assertTrue(any("allocated to multiple game days" in error for error in errors))

    def test_preview_reports_are_presented_as_readable_summaries(self):
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {
                "edition_id": self.edition.id,
                "structure_ids": [(6, 0, self.structure.ids)],
                "matchday_ids": [(6, 0, self.matchday.ids)],
                "allocation_report": [
                    {
                        "matchday_id": self.matchday.id,
                        "date": "2026-10-10",
                        "capacity": 10,
                        "included_fixture_count": 2,
                        "remaining_capacity": 8,
                    }
                ],
                "feasibility_report": {
                    "fixture_count": 2,
                    "included_fixture_count": 2,
                    "excluded_fixture_count": 0,
                    "deferred_fixture_count": 0,
                    "selected_stage_count": 1,
                    "available_slot_count": 10,
                    "capacity_surplus": 8,
                    "game_days": [],
                    "errors": [],
                },
                "quality_report": {
                    "warnings": [],
                    "teams_with_multiple_same_day_matches": 0,
                    "planned_fixture_counts": {str(self.matchday.id): 2},
                    "remaining_capacity": {str(self.matchday.id): 8},
                },
            }
        )

        self.assertIn(self.matchday.display_name, str(wizard.allocation_report_html))
        self.assertIn("Fixtures planned", str(wizard.allocation_report_html))
        self.assertIn("Playable fixtures", str(wizard.feasibility_report_html))
        self.assertIn("No quality warnings", str(wizard.quality_report_html))
