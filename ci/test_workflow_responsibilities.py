"""Focused workflow helper behavior; actual Odoo registry tests remain separate."""

import ast
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
import unittest

from ci.production_method import load_method, ROOT

SCHEDULE = "sports_federation_scheduling/wizards/competition_schedule_proposal.py"
PLANNER = "sports_federation_setup_flow/models/planner_readiness.py"
GAMEDAY = "sports_federation_rosters/models/match_sheet_gameday.py"


def translate(text, **values):
    return text % values if values else text


class TestWorkflowOwnership(unittest.TestCase):
    def test_extensions_keep_existing_models_and_import_order(self):
        for original, extension, model in (
            (
                "sports_federation_scheduling/wizards/competition_schedule_wizard.py",
                SCHEDULE,
                "federation.competition.schedule.wizard",
            ),
            (
                "sports_federation_setup_flow/models/planner_projection.py",
                PLANNER,
                "federation.competition.edition",
            ),
            (
                "sports_federation_rosters/models/match_sheet.py",
                GAMEDAY,
                "federation.match.sheet",
            ),
        ):
            with self.subTest(extension=extension):
                tree = ast.parse((ROOT / extension).read_text())
                cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
                assignments = {
                    node.targets[0].id: node.value
                    for node in cls.body
                    if isinstance(node, ast.Assign)
                    and isinstance(node.targets[0], ast.Name)
                }
                self.assertEqual(ast.literal_eval(assignments["_inherit"]), model)
                self.assertNotIn("_name", assignments)
                self.assertFalse(
                    any(
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "fields"
                        for node in ast.walk(cls)
                    )
                )
                init = (ROOT / Path(original).parent / "__init__.py").read_text()
                self.assertLess(
                    init.index("from . import " + Path(original).stem),
                    init.index("from . import " + Path(extension).stem),
                )
                original_tree = ast.parse((ROOT / original).read_text())
                original_names = {
                    node.name
                    for node in ast.walk(original_tree)
                    if isinstance(node, ast.FunctionDef)
                }
                moved_names = {
                    node.name for node in cls.body if isinstance(node, ast.FunctionDef)
                }
                self.assertFalse(original_names & moved_names)

    def test_read_only_projection_helpers_do_not_write(self):
        for path in (SCHEDULE, PLANNER):
            tree = ast.parse((ROOT / path).read_text())
            mutations = [
                node.func.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("create", "write", "unlink")
            ]
            self.assertEqual(mutations, [], path)


class TestScheduleProposal(unittest.TestCase):
    def test_duplicate_team_days_counts_each_team_per_day(self):
        teams = [SimpleNamespace(id=index) for index in (1, 2, 3)]
        fixtures = [
            SimpleNamespace(id=10, home_team_id=teams[0], away_team_id=teams[1]),
            SimpleNamespace(id=11, home_team_id=teams[0], away_team_id=teams[2]),
        ]
        duplicate = load_method(SCHEDULE, "_duplicate_team_days")
        self.assertEqual(duplicate(None, fixtures, {"assignments": {1: [10, 11]}}), 1)
        self.assertEqual(
            duplicate(None, fixtures, {"assignments": {1: [10], 2: [11]}}), 0
        )

    def test_invalid_proposal_retains_errors_and_empty_distribution(self):
        build = load_method(SCHEDULE, "_build_proposal", {"_": translate})
        wizard = SimpleNamespace(
            _validate_scope=lambda *args: (["Invalid scope"], []),
            _fixtures=lambda: ([], [], []),
            _capacities=lambda errors: [],
            _duplicate_team_days=lambda *args: 0,
            _rest_shortfalls=lambda *args: [],
            stage_ids=[],
        )
        proposal = build(wizard)
        self.assertEqual(proposal["errors"], ["Invalid scope"])
        self.assertFalse(proposal["distribution"]["valid"])
        self.assertEqual(proposal["feasibility"]["available_slot_count"], 0)
        self.assertEqual(proposal["allocation_report"], [])


class TestPlannerReadiness(unittest.TestCase):
    def setUp(self):
        self.steps = load_method(
            PLANNER, "_planner_steps", {"defaultdict": defaultdict}
        )
        label = load_method(PLANNER, "_planner_step_label", {"_": translate})
        self.planner = SimpleNamespace(
            _planner_step_label=lambda step: label(None, step)
        )
        self.counts = {"divisions": 1, "scheduled_gamedays": 1}
        self.rows = [{"teams_status": "complete", "format_status": "complete"}]

    def test_complete_steps_remain_complete(self):
        steps = self.steps(self.planner, self.counts, self.rows, [], [1])
        self.assertEqual([step["status"] for step in steps], ["complete"] * 6)

    def test_first_issue_is_current_and_later_steps_blocked(self):
        steps = self.steps(
            self.planner, self.counts, self.rows, [{"step": "schedule"}], [1]
        )
        by_key = {step["key"]: step for step in steps}
        self.assertEqual(by_key["schedule"]["status"], "current")
        self.assertEqual(by_key["publication"]["status"], "blocked")
        self.assertEqual(by_key["schedule"]["issue_count"], 1)

    def test_no_divisions_starts_at_basics(self):
        steps = self.steps(
            self.planner, {"divisions": 0, "scheduled_gamedays": 0}, [], [], []
        )
        self.assertEqual(steps[0]["status"], "current")
        self.assertTrue(all(step["status"] == "blocked" for step in steps[1:]))

    def test_issue_labels_follow_approval_setting(self):
        enrich = load_method(PLANNER, "_planner_enrich_issues", {"_": translate})
        for required, expected in (
            (True, "Submit schedule for review"),
            (False, "Publish schedule"),
        ):
            issues = enrich(
                SimpleNamespace(schedule_approval_required=required),
                [{"step": "publication"}],
            )
            self.assertEqual(issues[0]["action_label"], expected)
            self.assertEqual(issues[0]["owner"], "Schedule approver")


class TestGamedayDeclaration(unittest.TestCase):
    def test_explicit_matchday_wins_over_date_fallback(self):
        scope = load_method(GAMEDAY, "_get_gameday_scope")
        publication = SimpleNamespace(
            matchday_id=SimpleNamespace(id=8), _fields={"matchday_id": True}
        )
        match = SimpleNamespace(
            schedule_publication_id=publication,
            _fields={"schedule_publication_id": True},
        )
        self.assertEqual(
            scope(SimpleNamespace(ensure_one=lambda: None, match_id=match)),
            ("matchday", 8),
        )

    def test_date_fallback_uses_tournament(self):
        scope = load_method(
            GAMEDAY,
            "_get_gameday_scope",
            {
                "fields": SimpleNamespace(
                    Datetime=SimpleNamespace(to_datetime=datetime.fromisoformat)
                ),
            },
        )
        match = SimpleNamespace(
            _fields={},
            round_id=False,
            date_scheduled="2026-06-01 10:00:00",
            tournament_id=SimpleNamespace(id=9),
        )
        self.assertEqual(
            scope(SimpleNamespace(ensure_one=lambda: None, match_id=match)),
            ("tournament_date", 9, date(2026, 6, 1)),
        )

    def test_lineup_signature_is_independent_of_line_order(self):
        signature = load_method(GAMEDAY, "_declared_lineup_signature")

        def line(player):
            return SimpleNamespace(
                player_id=SimpleNamespace(id=player),
                roster_line_id=SimpleNamespace(id=player + 10),
                is_starter=True,
                is_substitute=False,
                is_captain=False,
                jersey_number="",
            )

        sheet = SimpleNamespace(
            ensure_one=lambda: None,
            roster_id=SimpleNamespace(id=4),
            line_ids=[line(2), line(1)],
        )
        first = signature(sheet)
        sheet.line_ids.reverse()
        self.assertEqual(signature(sheet), first)
        self.assertEqual(first[0], 4)
        self.assertEqual([row[0] for row in first[1]], [1, 2])


if __name__ == "__main__":
    unittest.main()
