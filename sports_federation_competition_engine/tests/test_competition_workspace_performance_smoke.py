import json
import time
from pathlib import Path

from odoo.tests import tagged

from .test_competition_workspace_service import TestCompetitionWorkspaceService


@tagged(
    "-at_install", "post_install", "sf_competition_workspace", "sf_planner_perf_smoke"
)
class TestCompetitionWorkspacePerformanceSmoke(TestCompetitionWorkspaceService):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        scenario_path = (
            Path(__file__).resolve().parent
            / "data"
            / "planner_performance_scenarios.json"
        )
        cls.performance_scenarios = json.loads(
            scenario_path.read_text(encoding="utf-8")
        )["scenarios"]

    def _prepare_perf_division(self, name, team_count):
        division, _participants = self._create_division(
            name,
            team_count,
            minimum_rest_minutes=30,
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

    def test_planner_payload_latency_smoke(self):
        scenario = self.performance_scenarios["planner_payload_smoke"]
        _, gameday = self._prepare_perf_division(
            "Perf Payload Division",
            scenario["team_count"],
        )

        start = time.perf_counter()
        planner = self.service.get_gameday_planner_data(gameday.id)
        elapsed = time.perf_counter() - start

        self.assertEqual(planner["gameday"]["id"], gameday.id)
        self.assertLessEqual(elapsed, scenario["max_elapsed_seconds"])

    def test_auto_schedule_latency_smoke(self):
        scenario = self.performance_scenarios["auto_schedule_smoke"]
        _, gameday = self._prepare_perf_division(
            "Perf Auto Schedule Division",
            scenario["team_count"],
        )

        start = time.perf_counter()
        result = self.service.auto_schedule_gameday(
            gameday.id,
            max_assignments=scenario["max_assignments"],
        )
        elapsed = time.perf_counter() - start

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["assigned_count"], 1)
        self.assertLessEqual(elapsed, scenario["max_elapsed_seconds"])
