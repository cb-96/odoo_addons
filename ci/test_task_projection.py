"""Execute production projection methods with isolated doubles, without Odoo.

These tests cover orchestration and writer semantics, not ORM authorization.
The installed portal TransactionCase tests cover actual source collection.
"""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

from ci.check_task_projection import violations

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "sports_federation_portal/models"
policy_spec = importlib.util.spec_from_file_location(
    "task_policy", ROOT / "sports_federation_portal/task_policy.py"
)
policy = importlib.util.module_from_spec(policy_spec)
policy_spec.loader.exec_module(policy)


def method(filename, name, namespace=None):
    tree = ast.parse((MODELS / filename).read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    module = ast.Module(body=[node], type_ignores=[])
    scope = dict(namespace or {})
    exec(compile(ast.fix_missing_locations(module), filename, "exec"), scope)
    return scope[name]


def spec(key="lineup:1", audience="club", task_type="gameday_lineup"):
    return dict(
        source_key=key, name="Line-up work", task_type=task_type, audience=audience,
        blocking_reason="Action required", next_step="Prepare line-up",
        source_model="federation.match.sheet", source_record_id=1,
    )


class Row:
    def __init__(self, values):
        self.__dict__.update(state="open", **values)
        self.writes = []

    def write(self, values):
        self.writes.append(dict(values))
        self.__dict__.update(values)


class Rows(list):
    def filtered(self, predicate):
        return Rows(row for row in self if predicate(row))

    def write(self, values):
        for row in self:
            row.write(values)


class Store:
    def __init__(self):
        self.rows = Rows()
        self.created = []

    def sudo(self):
        return self

    def search(self, domain):
        if domain and domain[0][0] == "source_key":
            return self.rows.filtered(lambda row: row.source_key in domain[0][2])
        if domain and domain[0][0] == "audience":
            return self.rows.filtered(lambda row: row.audience == domain[0][2])
        return Rows(self.rows)

    def create(self, values):
        self.created.append(dict(values))
        row = Row(values)
        self.rows.append(row)
        return row


class TestTaskProjection(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.writer = SimpleNamespace(env={"federation.operation.task": self.store})
        self.apply = method("task_projection_service.py", "_apply", {
            "task_policy": policy, "ValidationError": ValueError, "_": lambda text: text,
            "fields": SimpleNamespace(Datetime=SimpleNamespace(now=lambda: "now")),
        })

    def test_structure(self):
        self.assertEqual(violations(), [])

    def test_handoff_reuses_key_and_approval_closes(self):
        self.apply(self.writer, [spec()], [])
        row = self.store.rows[0]
        self.apply(self.writer, [spec(audience="manager", task_type="lineup_review")], [])
        self.assertIs(self.store.rows[0], row)
        self.assertEqual(len(self.store.created), 1)
        self.assertEqual(row.audience, "manager")
        self.apply(self.writer, [], [])
        self.assertEqual(row.state, "done")
        self.apply(self.writer, [spec()], [])
        self.assertEqual(row.state, "open")
        self.assertFalse(row.completed_on)
        self.assertFalse(row.digest_sent_on)

    def test_identical_duplicates_create_once(self):
        self.apply(self.writer, [spec(), spec()], [])
        self.assertEqual(len(self.store.created), 1)

    def test_invalid_spec_fails_before_any_write(self):
        self.store.create(spec("existing"))
        with self.assertRaises(ValueError):
            self.apply(self.writer, [spec(), dict(spec("bad"), next_step="")], [])
        self.assertEqual(len(self.store.created), 1)
        self.assertEqual(self.store.rows[0].writes, [])

    def test_conflicting_specs_fail_before_any_write(self):
        with self.assertRaises(ValueError):
            self.apply(self.writer, [spec(), dict(spec(), name="Conflicting")], [])
        self.assertEqual(self.store.created, [])

    def test_cleanup_does_not_close_other_scope(self):
        club = self.store.create(spec("club"))
        manager = self.store.create(spec("manager", "manager", "lineup_review"))
        self.apply(self.writer, [], [("audience", "=", "club")])
        self.assertEqual(club.state, "done")
        self.assertEqual(manager.state, "open")

    def test_nested_collection_keeps_invocations_independent(self):
        collect = method("task_projection.py", "_project_task_specs", {
            "expression": SimpleNamespace(OR=lambda scopes: scopes),
        })
        inner = SimpleNamespace(
            env=SimpleNamespace(user="inner"),
            _task_projection_collectors=lambda: ("domain",),
            domain=lambda user: ([spec("inner")], [("audience", "=", "manager")]),
        )
        nested = []

        def domain(user):
            nested.append(collect(inner, "inner"))
            return [spec("outer")], [("audience", "=", "club")]

        outer = SimpleNamespace(
            env=SimpleNamespace(user="outer"),
            _task_projection_collectors=lambda: ("domain", "missing_roster"),
            domain=domain,
            missing_roster=lambda user: ([spec("roster")], [("source_model", "=", "registration")]),
        )
        specs, scopes = collect(outer, "outer")
        self.assertEqual([item["source_key"] for item in specs], ["outer", "roster"])
        self.assertEqual(nested[0][0][0]["source_key"], "inner")
        self.assertEqual(len(scopes), 2)

    def test_unscoped_domain_collector_returns_safe_empty_scope(self):
        collect = method("task_projection.py", "_collect_domain_task_specs")
        user = SimpleNamespace(has_group=lambda group: False)
        task = SimpleNamespace(_portal_club_ids=lambda user: [])
        self.assertEqual(collect(task, user), ([], [("id", "=", 0)]))

    def test_collector_failure_prevents_writer_invocation(self):
        def fail(user):
            raise ValueError("collection failed")

        self.store._project_task_specs = fail
        calls = []
        service = SimpleNamespace(
            env={"federation.operation.task": self.store},
            _apply=lambda specs, scope: calls.append(specs),
        )
        synchronize = method("task_projection_service.py", "synchronize")
        with self.assertRaises(ValueError):
            synchronize(service, user="club")
        self.assertEqual(calls, [])

    def test_synchronize_collects_all_work_then_applies_once(self):
        events = []
        self.store._project_task_specs = lambda user: (events.append("collect") or (
            [spec(), dict(spec("hidden"), roster_id=42)], [("audience", "=", "club")]
        ))
        self.store._portal_get_domain = lambda user: [("audience", "=", "club")]
        archive = SimpleNamespace(hidden_roster_ids=lambda: [42], hidden_registration_ids=lambda: [])
        service = SimpleNamespace(env={
            "federation.operation.task": self.store, "federation.portal.archive.scope": archive,
        })
        applied = []
        service._apply = lambda specs, scope: (events.append("apply"), applied.append((specs, scope)))
        synchronize = method("task_projection_service.py", "synchronize")
        synchronize(service, user="club")
        self.assertEqual(events, ["collect", "apply"])
        self.assertEqual(len(applied), 1)
        self.assertEqual([item["source_key"] for item in applied[0][0]], ["lineup:1"])


if __name__ == "__main__":
    unittest.main()
