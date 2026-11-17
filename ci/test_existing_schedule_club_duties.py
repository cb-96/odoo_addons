#!/usr/bin/env python3
"""Execute published allocation guards and handoff without an Odoo runtime."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

source = (
    Path(__file__).resolve().parents[1]
    / "sports_federation_officiating/models/club_duty_planning.py"
)
tree = ast.parse(source.read_text())


class UserError(Exception):
    pass


def method(class_name, method_name):
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    node = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    node.decorator_list = []
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {"UserError": UserError, "_": lambda text: text}
    exec(compile(ast.fix_missing_locations(module), str(source), "exec"), namespace)
    return namespace[method_name]


class Duties(list):
    def action_open(self):
        for duty in self:
            duty.opened += 1


class DutyModel:
    def __init__(self):
        self.created = Duties()

    def create(self, values):
        self.created = Duties(
            SimpleNamespace(values=value, opened=0, message_post=lambda **kw: None)
            for value in values
        )
        return self.created

    def browse(self, ids):
        return Duties()


class TestPublishedHandoff(unittest.TestCase):
    def schedule(self):
        schedule = SimpleNamespace(state="published", ensure_one=lambda: None)
        publication = SimpleNamespace(state="live", schedule_id=schedule)
        schedule.matchday_id = SimpleNamespace(current_publication_id=publication)
        return schedule

    def test_current_publication_is_accepted(self):
        schedule = self.schedule()
        publication = method("ScheduleClubDutyPlan", "_live_duty_publication")(schedule)
        self.assertIs(publication, schedule.matchday_id.current_publication_id)

    def test_superseded_publication_is_rejected(self):
        schedule = self.schedule()
        schedule.matchday_id.current_publication_id.state = "superseded"
        with self.assertRaises(UserError):
            method("ScheduleClubDutyPlan", "_live_duty_publication")(schedule)

    def test_different_schedule_is_rejected(self):
        schedule = self.schedule()
        schedule.matchday_id.current_publication_id.schedule_id = object()
        with self.assertRaises(UserError):
            method("ScheduleClubDutyPlan", "_live_duty_publication")(schedule)

    def test_draft_cannot_use_live_route(self):
        schedule = self.schedule()
        schedule.state = "draft"
        with self.assertRaises(UserError):
            method("ScheduleClubDutyPlan", "_live_duty_publication")(schedule)

    def test_apply_creates_reviewed_roles_and_opens_once(self):
        model = DutyModel()
        wizard = SimpleNamespace(env={"federation.match.club.referee.duty": model})
        schedule = SimpleNamespace(_live_duty_publication=lambda: True)
        row = {"match": 7, "club": 3, "roles": ["head", "assistant_1"]}
        method("ClubDutyReview", "_apply_live_duties")(
            wizard, schedule, {"rows": [row]}
        )
        self.assertEqual(len(model.created), 2)
        self.assertEqual([d.values["role"] for d in model.created], row["roles"])
        self.assertTrue(all(d.opened == 1 for d in model.created))
        self.assertTrue(
            all(d.values["allocation_snapshot"] == row for d in model.created)
        )
        # schedule has no write method: any attempt to rewrite it would fail.

    def test_empty_proposal_creates_nothing(self):
        model = DutyModel()
        wizard = SimpleNamespace(env={"federation.match.club.referee.duty": model})
        schedule = SimpleNamespace(_live_duty_publication=lambda: True)
        method("ClubDutyReview", "_apply_live_duties")(wizard, schedule, {"rows": []})
        self.assertFalse(model.created)


if __name__ == "__main__":
    unittest.main()
