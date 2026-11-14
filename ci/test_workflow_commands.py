"""Behavioral tests of production schedule commands and transition mechanics."""

import ast
from contextlib import contextmanager
from functools import wraps
from types import SimpleNamespace
import unittest

from ci.production_method import load_method, ROOT

SCHEDULE = "sports_federation_scheduling/services/schedule_commands.py"
TRANSITION = "sports_federation_base/models/workflow_transition.py"


def translate(text, **values):
    return text % values if values else text


class TestScheduleSubmission(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.schedule = SimpleNamespace(id=7, state="draft")
        self.validation = {"valid": True, "warnings": []}

        def execute(schedule, target, allowed, **kwargs):
            self.events.append(("transition", target, allowed, kwargs))
            schedule.state = target

        self.service = SimpleNamespace(
            env={
                "federation.schedule.validator": SimpleNamespace(
                    validate_map=lambda *args: self.validation
                ),
                "federation.schedule.change": SimpleNamespace(
                    create=lambda values: self.events.append(("override", values))
                ),
                "federation.workflow.transition": SimpleNamespace(execute=execute),
                "federation.competition.event": SimpleNamespace(
                    emit=lambda *args: self.events.append(("event", args))
                ),
            },
            _resolve=lambda *args: (self.schedule, 4),
            _map=lambda schedule: {},
        )
        self.submit = load_method(
            SCHEDULE, "submit", {"ValidationError": ValueError, "_": translate}
        )

    def test_submission_uses_transition_with_revision_and_audit(self):
        result = self.submit(self.service, 7, 3)
        self.assertEqual(
            result, {"schedule_id": 7, "revision": 4, "state": "ready_for_review"}
        )
        kind, target, allowed, kwargs = self.events[0]
        self.assertEqual(kind, "transition")
        self.assertEqual(target, "ready_for_review")
        self.assertEqual(allowed, {"draft", "changes_requested"})
        self.assertEqual(kwargs["expected_revision"], 4)
        self.assertEqual(kwargs["event_type"], "schedule_submitted")
        self.assertEqual(self.events[1][0], "event")

    def test_invalid_schedule_has_no_transition_or_event(self):
        self.validation["valid"] = False
        with self.assertRaises(ValueError):
            self.submit(self.service, 7, 3)
        self.assertEqual(self.events, [])
        self.assertEqual(self.schedule.state, "draft")

    def test_warning_requires_nonblank_reason(self):
        self.validation["warnings"] = ["short rest"]
        for reason in (False, "", "  "):
            with self.assertRaises(ValueError):
                self.submit(self.service, 7, 3, reason)
        self.assertEqual(self.events, [])

    def test_override_evidence_precedes_transition(self):
        self.validation["warnings"] = ["short rest"]
        self.submit(self.service, 7, 3, "Approved exception")
        self.assertEqual(
            [item[0] for item in self.events], ["override", "transition", "event"]
        )
        self.assertEqual(self.events[0][1]["reason"], "Approved exception")
        self.assertEqual(self.events[0][1]["revision"], 4)

    def test_resolution_failure_prevents_side_effects(self):
        def reject(*args):
            raise ValueError("stale or unauthorized")

        self.service._resolve = reject
        with self.assertRaises(ValueError):
            self.submit(self.service, 7, 3)
        self.assertEqual(self.events, [])

    def test_atomic_decorator_rolls_back_revision_when_validation_fails(self):
        @contextmanager
        def savepoint():
            state = self.schedule.state
            revision = self.schedule.revision
            try:
                yield
            except Exception:
                self.schedule.state = state
                self.schedule.revision = revision
                raise

        self.schedule.revision = 3
        self.service.env = SimpleEnv(self.service.env, savepoint)

        def resolve(*args):
            self.schedule.revision += 1
            return self.schedule, self.schedule.revision

        self.service._resolve = resolve
        self.validation["valid"] = False
        atomic = load_method(SCHEDULE, "atomic_command", {"wraps": wraps})
        decorated = load_method(
            SCHEDULE,
            "submit",
            {
                "atomic_command": atomic,
                "api": SimpleNamespace(model=lambda fn: fn),
                "ValidationError": ValueError,
                "_": translate,
            },
            keep_decorators=True,
        )
        with self.assertRaises(ValueError):
            decorated(self.service, 7, 3)
        self.assertEqual(self.schedule.revision, 3)
        self.assertEqual(self.events, [])

    def test_behavior_detects_removed_warning_guard(self):
        tree = ast.parse((ROOT / SCHEDULE).read_text())
        submit = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "submit"
        )
        guard = next(
            node
            for node in submit.body
            if isinstance(node, ast.If) and isinstance(node.test, ast.BoolOp)
        )
        guard.test = ast.Constant(False)
        mutant = load_method(
            SCHEDULE,
            "submit",
            {"ValidationError": ValueError, "_": translate},
            source=ast.unparse(ast.fix_missing_locations(tree)),
        )
        self.validation["warnings"] = ["short rest"]
        # The mutant proceeds, demonstrating why the rejection test matters.
        mutant(self.service, 7, 3)
        self.assertNotEqual(self.events, [])


class SimpleEnv(dict):
    def __init__(self, values, savepoint):
        super().__init__(values)
        self.cr = SimpleNamespace(savepoint=savepoint)


class Records(list):
    _name = "test.workflow"

    def exists(self):
        return self

    def filtered(self, predicate):
        return Records(row for row in self if predicate(row))

    def mapped(self, field):
        return [row[field] for row in self]

    @property
    def ids(self):
        return [row.id for row in self]

    def write(self, values):
        for row in self:
            row.values.update(values)


class Row:
    id = 1

    def __init__(self, **values):
        self.values = values

    def __getitem__(self, field):
        return self.values[field]


class TestWorkflowTransition(unittest.TestCase):
    def setUp(self):
        self.actor = SimpleNamespace(id=8)
        self.records = Records([Row(state="draft", revision=3, submitted_by=False)])
        self.audit = []

        class Env(dict):
            user = self.actor

        self.service = SimpleNamespace(
            env=Env(
                {
                    "federation.audit.event": SimpleNamespace(
                        log_record_events=lambda **kwargs: self.audit.append(kwargs)
                    ),
                }
            )
        )
        self.execute = load_method(
            TRANSITION,
            "execute",
            {
                "ValidationError": ValueError,
                "_": translate,
                "fields": SimpleNamespace(Datetime=SimpleNamespace(now=lambda: "now")),
            },
        )

    def assert_rejected(self, **kwargs):
        before = dict(self.records[0].values)
        with self.assertRaises(ValueError):
            self.execute(self.service, self.records, "ready", {"draft"}, **kwargs)
        self.assertEqual(self.records[0].values, before)
        self.assertEqual(self.audit, [])

    def test_stale_revision_is_rejected_before_write(self):
        self.assert_rejected(expected_revision=2)

    def test_reason_is_required_before_write(self):
        self.assert_rejected(reason_required=True, reason="  ")

    def test_separation_of_duties_is_enforced(self):
        self.records[0].values["submitted_by"] = self.actor
        self.assert_rejected(forbidden_actor_fields=["submitted_by"])

    def test_invalid_source_state_is_rejected(self):
        self.records[0].values["state"] = "archived"
        self.assert_rejected()

    def test_transition_writes_and_audits_actor(self):
        result = self.execute(
            self.service,
            self.records,
            "ready",
            {"draft"},
            expected_revision=3,
            event_type="submitted",
            reason=" Reviewed ",
        )
        self.assertEqual(self.records[0]["state"], "ready")
        self.assertEqual(result["reason"], "Reviewed")
        self.assertEqual(result["previous_states"], {"1": "draft"})
        self.assertIs(self.audit[0]["actor"], self.actor)
        self.assertEqual(self.audit[0]["event_type"], "submitted")

    def test_custom_writer_is_used(self):
        writes = []
        self.execute(
            self.service, self.records, "ready", {"draft"}, writer=writes.append
        )
        self.assertEqual(writes, [{"state": "ready"}])
        self.assertEqual(self.records[0]["state"], "draft")


if __name__ == "__main__":
    unittest.main()
