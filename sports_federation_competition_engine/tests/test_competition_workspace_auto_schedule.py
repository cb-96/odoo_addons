from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("-at_install", "post_install", "sf_competition_workspace")
class TestCompetitionWorkspaceAutoSchedule(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["federation.competition.workspace.service"]
        cls.club = cls.env["federation.club"].create({"name": "Workspace Club Auto"})
        cls.teams = cls.env["federation.team"]
        for index in range(1, 9):
            cls.teams |= cls.env["federation.team"].create(
                {
                    "name": f"Workspace Auto Team {index}",
                    "club_id": cls.club.id,
                }
            )

        cls.season = cls.env["federation.season"].create(
            {
                "name": "2026-2027 Auto",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        cls.competition_template = cls.env["federation.competition"].create(
            {
                "name": "Workspace Auto League",
                "competition_type": "league",
            }
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Workspace Auto League 2026",
                "competition_id": cls.competition_template.id,
                "season_id": cls.season.id,
                "date_start": "2026-10-01",
                "date_end": "2027-04-30",
            }
        )
        cls.venue = cls.env["federation.venue"].create({"name": "Central Hall Auto"})
        cls.court_1 = cls.env["federation.playing.area"].create(
            {"name": "Court 1 Auto", "venue_id": cls.venue.id}
        )
        cls.court_2 = cls.env["federation.playing.area"].create(
            {"name": "Court 2 Auto", "venue_id": cls.venue.id}
        )

    def _create_division(
        self,
        name,
        team_count,
        team_offset=0,
        minimum_rest_minutes=30,
        max_consecutive_matches_per_team=1,
        planning_format="single_round_robin",
    ):
        division = self.env["federation.tournament"].create(
            {
                "name": name,
                "edition_id": self.edition.id,
                "competition_id": self.competition_template.id,
                "season_id": self.season.id,
                "date_start": "2026-10-10",
                "date_end": "2026-10-10",
                "planning_format": planning_format,
                "workspace_state": "registration_open",
                "minimum_rest_minutes": minimum_rest_minutes,
                "max_consecutive_matches_per_team": max_consecutive_matches_per_team,
            }
        )
        participants = self.env["federation.tournament.participant"]
        for seed, team in enumerate(
            self.teams[team_offset : team_offset + team_count],
            start=1,
        ):
            participants |= self.env["federation.tournament.participant"].create(
                {
                    "tournament_id": division.id,
                    "team_id": team.id,
                    "seed": seed,
                    "state": "confirmed",
                }
            )
        return division, participants

    def _prepare_planned_division(self, name="Planner Division"):
        division, _participants = self._create_division(
            name, 4, minimum_rest_minutes=30
        )
        division.action_lock_team_entries()
        self.service.generate_round_robin(division.id)
        gameday_id = self.service.create_gameday(
            {
                "division_id": division.id,
                "name": "Gameday 1",
                "round_date": "2026-10-10",
                "venue_id": self.venue.id,
            }
        )["gameday_id"]
        self.service.generate_slots(
            gameday_id,
            [self.court_1.id, self.court_2.id],
            "09:00",
            "10:20",
            30,
            5,
            [],
            False,
        )
        return division, self.env["federation.tournament.round"].browse(gameday_id)

    def test_auto_schedule_gameday_assigns_only_active_gameday_round_slice(self):
        division, first_gameday = self._prepare_planned_division(
            "Auto Schedule Slice Division"
        )
        second_gameday_id = self.service.create_gameday(
            {
                "division_id": division.id,
                "name": "Gameday 2",
                "round_date": "2026-10-17",
            }
        )["gameday_id"]
        second_gameday = self.env["federation.tournament.round"].browse(
            second_gameday_id
        )
        self.service.generate_slots(
            second_gameday.id,
            [self.court_1.id, self.court_2.id],
            "09:00",
            "10:20",
            30,
            5,
            [],
            False,
        )

        result = self.service.auto_schedule_gameday(first_gameday.id)

        self.assertTrue(result["ok"])
        self.assertEqual(result["assigned_count"], 2)
        self.assertEqual(len(result["assigned_matches"]), 2)
        self.assertEqual(
            {
                "min_rest_gap_minutes",
                "total_rest_gap_minutes",
                "home_away_delta",
                "slot_start",
            },
            set(result["assigned_matches"][0]["score"].keys()),
        )
        scheduled_round_numbers = set(
            division.match_ids.filtered("slot_id").mapped("round_number")
        )
        self.assertEqual(scheduled_round_numbers, {first_gameday.sequence})
        self.assertEqual(
            len(second_gameday.slot_ids.filtered("match_id")),
            0,
        )

    def test_auto_schedule_gameday_uses_candidate_scoring(self):
        division, _participants = self._create_division(
            "Auto Schedule Scoring Division",
            4,
            minimum_rest_minutes=0,
        )
        division.action_lock_team_entries()
        self.service.generate_round_robin(division.id)
        gameday_id = self.service.create_gameday(
            {
                "division_id": division.id,
                "name": "Scoring Gameday 1",
                "round_date": "2026-10-10",
                "venue_id": self.venue.id,
            }
        )["gameday_id"]
        gameday = self.env["federation.tournament.round"].browse(gameday_id)
        self.service.generate_slots(
            gameday.id,
            [self.court_1.id],
            "09:00",
            "11:00",
            30,
            0,
            [],
            False,
        )

        unscheduled = self.service._get_gameday_unscheduled_matches(gameday)
        penalized_match = unscheduled[0]
        preferred_match = unscheduled[1]

        earliest_slot = gameday.slot_ids.sorted(lambda slot: slot.start_datetime)[0]
        next_slot = gameday.slot_ids.sorted(lambda slot: slot.start_datetime)[1]
        for slot in gameday.slot_ids - earliest_slot - next_slot:
            slot.write({"state": "blocked"})

        extra_team = self.env["federation.team"].create(
            {
                "name": "Auto Schedule Seed Team",
                "club_id": self.club.id,
            }
        )
        prior_match = self.env["federation.match"].create(
            {
                "tournament_id": division.id,
                "home_team_id": penalized_match.home_team_id.id,
                "away_team_id": extra_team.id,
                "round_number": 99,
            }
        )
        prior_match.write(
            {
                "slot_id": earliest_slot.id,
                "round_id": gameday.id,
                "date_scheduled": earliest_slot.start_datetime,
            }
        )
        earliest_slot.write({"match_id": prior_match.id})

        result = self.service.auto_schedule_gameday(gameday.id, max_assignments=1)

        self.assertTrue(result["ok"])
        self.assertEqual(result["assigned_count"], 1)
        self.assertEqual(len(result["assigned_matches"]), 1)
        self.assertEqual(result["assigned_matches"][0]["match_id"], preferred_match.id)
        self.assertIn("home_away_delta", result["assigned_matches"][0]["score"])
        self.assertIn("min_rest_gap_minutes", result["assigned_matches"][0]["score"])
        self.assertEqual(next_slot.match_id.id, preferred_match.id)
        self.assertFalse(penalized_match.slot_id)

    def test_auto_schedule_gameday_assigns_when_only_warnings_exist(self):
        _division, gameday = self._prepare_planned_division(
            "Auto Schedule Warning-Only Division"
        )

        warning_validation = self.service._planner_validation(
            warnings=[
                {
                    "code": "short_rest_warning",
                    "message": "Short rest window detected.",
                }
            ]
        )

        with patch.object(
            type(self.service),
            "_validate_assignment_action",
            return_value=warning_validation,
        ):
            result = self.service.auto_schedule_gameday(gameday.id, max_assignments=1)

        self.assertTrue(result["ok"])
        self.assertEqual(result["assigned_count"], 1)
        self.assertEqual(len(result["assigned_matches"]), 1)
        self.assertEqual(result["assigned_matches"][0]["warning_count"], 1)
        self.assertIn(
            "short_rest_warning",
            result["assigned_matches"][0]["warning_codes"],
        )

    def test_auto_schedule_gameday_includes_fairness_and_repair_diagnostics(self):
        _division, gameday = self._prepare_planned_division(
            "Auto Schedule Diagnostics Division"
        )

        result = self.service.auto_schedule_gameday(
            gameday.id,
            config={
                "solver_mode": "advanced",
                "enable_repair": True,
                "repair_step_limit": 25,
                "weights": {
                    "rest_fairness": 1.5,
                    "home_away_fairness": 1.0,
                    "timeslot_fairness": 0.75,
                    "warning_penalty": 30,
                },
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["assigned_count"], 2)
        self.assertIn("fairness_before", result)
        self.assertIn("fairness_after", result)
        self.assertIn("fairness_delta", result)
        self.assertIn("repair", result)
        self.assertIn("augmentation", result)
        self.assertIn("auto_schedule_config", result)
        self.assertEqual(result["auto_schedule_config"]["solver_mode"], "advanced")
        self.assertTrue(result["auto_schedule_config"]["enable_repair"])
        self.assertTrue(result["auto_schedule_config"]["enable_augmentation"])
        self.assertEqual(result["auto_schedule_config"]["repair_step_limit"], 25)
        self.assertIn("objective_penalty", result["assigned_matches"][0])
        self.assertIn("objective_components", result["assigned_matches"][0])

    def test_auto_schedule_gameday_rejects_unknown_weight_keys(self):
        _division, gameday = self._prepare_planned_division(
            "Auto Schedule Invalid Config Division"
        )

        with self.assertRaises(ValidationError):
            self.service.auto_schedule_gameday(
                gameday.id,
                config={
                    "weights": {
                        "unknown_weight": 1,
                    }
                },
            )

    def test_auto_schedule_repair_pass_applies_improving_swap(self):
        _division, gameday = self._prepare_planned_division(
            "Auto Schedule Repair Swap Division"
        )
        unscheduled = self.service._get_gameday_unscheduled_matches(gameday)
        slots = gameday.slot_ids.sorted(lambda slot: slot.start_datetime)
        self.assertTrue(
            self.service.assign_match_to_slot(unscheduled[0].id, slots[0].id)["ok"]
        )
        self.assertTrue(
            self.service.assign_match_to_slot(unscheduled[1].id, slots[1].id)["ok"]
        )

        scheduled_matches = list(self.service._get_gameday_scheduled_matches(gameday))
        self.assertEqual(len(scheduled_matches), 2)
        first_match = scheduled_matches[0]
        second_match = scheduled_matches[1]
        first_slot = first_match.slot_id
        second_slot = second_match.slot_id

        slot_by_match = {
            first_match.id: first_slot,
            second_match.id: second_slot,
        }
        match_lookup = {
            first_match.id: first_match,
            second_match.id: second_match,
        }

        def _fake_objective(_service, slot_map, _lookup, _weights):
            swapped = (
                slot_map.get(first_match.id) == second_slot
                and slot_map.get(second_match.id) == first_slot
            )
            penalty = 0.0 if swapped else 100.0
            return {
                "tracked_team_count": 2,
                "component_penalties": {
                    "rest_fairness": penalty,
                    "home_away_fairness": 0.0,
                    "timeslot_fairness": 0.0,
                },
                "weighted_component_penalties": {
                    "rest_fairness": penalty,
                    "home_away_fairness": 0.0,
                    "timeslot_fairness": 0.0,
                },
                "total_penalty": penalty,
            }

        resolved_config = self.service._auto_schedule_resolve_config(
            {
                "solver_mode": "hybrid",
                "enable_repair": True,
                "repair_step_limit": 10,
            }
        )

        with patch.object(
            type(self.service),
            "_auto_schedule_objective_from_slot_map",
            autospec=True,
            side_effect=_fake_objective,
        ):
            summary = self.service._auto_schedule_repair_assignments(
                self.service._get_planner_root_gameday(gameday),
                slot_by_match,
                match_lookup,
                self.service._check_access(),
                resolved_config,
                batch_key="repair-swap-test",
            )

        self.assertGreaterEqual(summary["applied_moves"], 1)
        self.assertLess(
            summary["after_objective_penalty"], summary["before_objective_penalty"]
        )
        self.assertEqual(
            self.env["federation.match"].browse(first_match.id).slot_id.id,
            second_slot.id,
        )
        self.assertEqual(
            self.env["federation.match"].browse(second_match.id).slot_id.id,
            first_slot.id,
        )

    def test_auto_schedule_augmentation_rearranges_to_assign_all_matches(self):
        division, gameday = self._prepare_planned_division(
            "Auto Schedule Augmentation Division"
        )
        teams = division.participant_ids.mapped("team_id")
        self.env["federation.match"].create(
            {
                "tournament_id": division.id,
                "home_team_id": teams[0].id,
                "away_team_id": teams[2].id,
                "stage_id": gameday.stage_id.id,
                "round_number": gameday.sequence,
            }
        )

        slots = gameday.slot_ids.sorted(lambda slot: slot.start_datetime)
        for slot in slots[3:]:
            slot.write({"state": "blocked"})

        unscheduled = self.service._get_gameday_unscheduled_matches(gameday)
        self.assertGreaterEqual(len(unscheduled), 3)
        m1, m2, m3 = unscheduled[:3]
        s1, s2, s3 = slots[:3]

        allowed_slots = {
            m1.id: {s1.id, s3.id},
            m2.id: {s1.id},
            m3.id: {s2.id},
        }

        def _fake_validate(
            service,
            match,
            slot,
            _capabilities,
            force=False,
            override_reason=False,
            **kwargs,
        ):
            del force, override_reason, kwargs
            allowed = allowed_slots.get(match.id)
            if allowed and slot.id not in allowed:
                return service._planner_validation(
                    blocking=[
                        {
                            "code": "no_feasible_slot",
                            "message": "No feasible slot for this match.",
                        }
                    ]
                )
            return service._planner_validation()

        def _fake_score(_service, match, slot, _balances, breakdown=False):
            del breakdown
            priority = 200 if (match.id == m1.id and slot.id == s1.id) else 0
            return (priority, 0, 0, 0, 0)

        with patch.object(
            type(self.service),
            "_validate_assignment_action",
            autospec=True,
            side_effect=_fake_validate,
        ), patch.object(
            type(self.service),
            "_auto_schedule_candidate_score",
            autospec=True,
            side_effect=_fake_score,
        ):
            result = self.service.auto_schedule_gameday(gameday.id)

        self.assertTrue(result["ok"])
        self.assertEqual(result["assigned_count"], 3)
        self.assertEqual(result["remaining_unscheduled_count"], 0)
        self.assertGreaterEqual(result["augmentation"]["newly_assigned_count"], 1)
        self.assertGreaterEqual(result["augmentation"]["reassigned_count"], 1)
        self.assertEqual(m2.slot_id.id, s1.id)
        self.assertEqual(m3.slot_id.id, s2.id)
        self.assertEqual(m1.slot_id.id, s3.id)

    def test_auto_schedule_home_away_delta_prefers_balance_improving_pairings(self):
        division, gameday = self._prepare_planned_division(
            "Auto Schedule Balance Division"
        )
        match = self.service._get_gameday_unscheduled_matches(gameday)[0]

        worsening_delta = self.service._auto_schedule_home_away_delta(
            match,
            {
                match.home_team_id.id: {"home": 5, "away": 1, "last_end": False},
                match.away_team_id.id: {"home": 1, "away": 5, "last_end": False},
            },
        )
        improving_delta = self.service._auto_schedule_home_away_delta(
            match,
            {
                match.home_team_id.id: {"home": 1, "away": 5, "last_end": False},
                match.away_team_id.id: {"home": 5, "away": 1, "last_end": False},
            },
        )

        self.assertLess(worsening_delta, 0)
        self.assertGreater(improving_delta, 0)
