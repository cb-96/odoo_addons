"""Production-method tests with doubles; not ORM, SQL or browser qualification."""
import ast
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from functools import wraps
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from xml.etree import ElementTree

from ci.production_method import load_method, ROOT

MODELS = "sports_federation_notifications/models/"
NOW = datetime(2026, 11, 6, 12)


class RetryTransaction(Exception):
    pass


def method(name, file="notification_operations.py", **extra):
    return load_method(MODELS + file, name, {
        "_": lambda text: text, "AccessError": PermissionError,
        "DeadlockDetected": RetryTransaction, "SerializationFailure": RetryTransaction,
        "build_failure_feedback": lambda error: ("unexpected_bug", "Operator-safe failure"),
        "_logger": logging.getLogger("notification_operations_test"),
        "fields": SimpleNamespace(Datetime=SimpleNamespace(now=lambda: NOW)),
        "delivery_label": lambda state: state,
        **extra,
    })


class Records(list):
    _name = "test.records"
    @property
    def ids(self):
        return [row.id for row in self]
    def filtered(self, predicate):
        return Records(row for row in self if predicate(row))
    def mapped(self, field):
        return Records(getattr(row, field) for row in self)
    def __getitem__(self, key):
        result = super().__getitem__(key)
        return Records(result) if isinstance(key, slice) else result
    def sudo(self):
        return self
    def exists(self):
        return self
    def browse(self):
        return Records()


class TestBoundary(unittest.TestCase):
    def setUp(self):
        self.data = {"decision": "committed in transaction", "notification": None}
        self.logs = []
        self.evidence_failure = False
        @contextmanager
        def savepoint():
            before = deepcopy(self.data)
            try:
                yield
            except Exception:
                self.data.clear()
                self.data.update(before)
                raise
        test = self
        class Log:
            _name = "federation.notification.log"
            def sudo(self): return self
            def browse(self): return self
            def create(self, values):
                if test.evidence_failure: raise RuntimeError("evidence unavailable")
                test.logs.append(values)
                return SimpleNamespace(**values)
        class Env(dict):
            cr = SimpleNamespace(savepoint=savepoint)
        self.service = SimpleNamespace(env=Env({"federation.notification.log": Log(), "receipt": Records()}))
        self.run = method("_run_notification_effect")

    def test_success_returns_callback_value(self):
        self.assertEqual(self.run(self.service, lambda: "queued"), "queued")
        self.assertEqual(self.logs, [])

    def test_failure_rolls_back_only_notification_changes(self):
        def fail():
            self.data["notification"] = "partial"
            raise RuntimeError("routing failed")
        with self.assertLogs("notification_operations_test", level="ERROR"):
            result = self.run(self.service, fail)
        self.assertEqual(self.data["decision"], "committed in transaction")
        self.assertIsNone(self.data["notification"])
        self.assertEqual(result.state, "failed")
        self.assertEqual(result.operator_message, "Operator-safe failure")

    def test_evidence_failure_does_not_escape(self):
        self.evidence_failure = True
        with self.assertLogs("notification_operations_test", level="ERROR"):
            self.run(self.service, lambda: (_ for _ in ()).throw(RuntimeError("failure")))
        self.assertEqual(self.data["decision"], "committed in transaction")

    def test_framework_retry_is_not_swallowed(self):
        with self.assertRaises(RetryTransaction):
            self.run(self.service, lambda: (_ for _ in ()).throw(RetryTransaction()))
        self.assertEqual(self.logs, [])

    def test_receipt_producer_returns_empty_receipt_on_failure(self):
        with self.assertLogs("notification_operations_test", level="ERROR"):
            result = self.run(self.service, lambda: (_ for _ in ()).throw(RuntimeError()), fallback_model="receipt")
        self.assertEqual(result, [])
        self.assertEqual(self.logs[0]["state"], "failed")

    def test_decorator_preserves_name_and_calls_boundary(self):
        decorator = load_method(MODELS + "notification_boundary.py", "notification_effect", {"wraps": wraps})
        calls = []
        service = SimpleNamespace(_run_notification_effect=lambda callback, **kw: calls.append(kw) or callback())
        recordset = SimpleNamespace(env={"federation.notification.service": service})
        @decorator()
        def send_example(self): return "queued"
        self.assertEqual(send_example(recordset), "queued")
        self.assertEqual(send_example.__name__, "send_example")
        self.assertEqual(calls[0]["name"], "send_example")


class Receipt:
    def __init__(self, ident, allowed=True):
        self.id = ident
        self.allowed = allowed
        self.delivery_ids = []
        self.presented = 0
    def _presentation(self, user):
        self.presented += 1
        if not self.allowed: raise PermissionError("revoked")
        return {"task_state": "open"}


class InboxStore:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
    def search(self, domain, order, limit):
        self.calls.append((domain, order, limit))
        before = min([value for field, op, value in domain if field == "id" and op == "<"] or [10**9])
        return [row for row in self.rows if row.id < before][:limit]


class TestInbox(unittest.TestCase):
    def page(self, rows, **kwargs):
        self.store = InboxStore(rows)
        self.user = SimpleNamespace(id=7)
        class Env(dict): pass
        env = Env({"federation.communication.receipt": self.store})
        env.user = self.user
        return method("_inbox_page")(SimpleNamespace(env=env), self.user, **kwargs)

    def test_visible_page_is_bounded(self):
        rows = [Receipt(i) for i in range(1000, 0, -1)]
        page = self.page(rows)
        self.assertEqual(len(page["items"]), 20)
        self.assertEqual(sum(row.presented for row in rows), 20)
        self.assertEqual([call[2] for call in self.store.calls], [200, 1])

    def test_all_revoked_window_is_bounded_and_continues(self):
        rows = [Receipt(i, False) for i in range(1000, 0, -1)]
        page = self.page(rows)
        self.assertEqual(page["items"], [])
        self.assertEqual(sum(row.presented for row in rows), 200)
        self.assertEqual(page["next_before"], 801)

    def test_next_page_has_no_overlap(self):
        rows = [Receipt(i) for i in range(45, 0, -1)]
        first = self.page(rows)
        second = self.page(rows, before=first["next_before"])
        self.assertFalse({item["receipt"].id for item in first["items"]} &
                         {item["receipt"].id for item in second["items"]})

    def test_small_final_page_has_no_continuation(self):
        page = self.page([Receipt(1)])
        self.assertFalse(page["next_before"])
        self.assertEqual(len(self.store.calls), 1)

    def test_requested_page_size_is_capped(self):
        self.assertEqual(len(self.page([Receipt(i) for i in range(50, 0, -1)], limit=500)["items"]), 20)

    def test_owner_and_status_are_in_query(self):
        self.page([Receipt(1)], status="unacknowledged")
        self.assertIn(("recipient_id", "=", 7), self.store.calls[0][0])
        self.assertIn(("acknowledged_on", "=", False), self.store.calls[0][0])

    def test_other_user_is_rejected(self):
        env = SimpleNamespace(user=SimpleNamespace(id=1))
        with self.assertRaises(PermissionError):
            method("_inbox_page")(SimpleNamespace(env=env), SimpleNamespace(id=2))


class TestDigest(unittest.TestCase):
    def test_manager_refresh_once_and_user_failure_isolated(self):
        users = Records([SimpleNamespace(id=i, has_group=lambda group: True) for i in range(1, 4)])
        refreshes, processed, errors = [], [], []
        tasks = SimpleNamespace(sudo=lambda: tasks,
            sync_for_user=lambda **kwargs: refreshes.append(kwargs) or SimpleNamespace(_name="federation.operation.task"))
        user_model = SimpleNamespace(sudo=lambda: user_model, search=lambda domain: users)
        preferences = SimpleNamespace(sudo=lambda: preferences, search=lambda domain: [])
        service = SimpleNamespace(env={"res.users": user_model, "federation.operation.task": tasks,
                                       "federation.communication.preference": preferences})
        service.with_context = lambda **kwargs: service
        def boundary(callback, **kwargs):
            try: return callback()
            except RuntimeError: errors.append("isolated")
        service._run_notification_effect = boundary
        def digest(user, now, tasks):
            processed.append(user.id)
            if user.id == 2: raise RuntimeError("one user failed")
        service._digest_for_user = digest
        method("_cron_action_digests", file="communication_service.py")(service)
        self.assertEqual(len(refreshes), 1)
        self.assertEqual(processed, [1, 2, 3])
        self.assertEqual(errors, ["isolated"])

    def test_cached_defaults_preserve_due_soon_digest_and_failure_inbox(self):
        mode = method("_mode_for", file="actionable_communications.py")
        preference = SimpleNamespace(env=SimpleNamespace(su=True, context={"notification_preference_modes": {}}))
        user = SimpleNamespace(id=7)
        self.assertEqual(mode(preference, user, "due_soon"), "digest")
        self.assertEqual(mode(preference, user, "delivery_failure"), "inbox")
        self.assertEqual(mode(preference, user, "schedule_change"), "immediate")


class TestMailRetention(unittest.TestCase):
    def run_cleanup(self, state="sent", owned=True, logs=0, deliveries=0, locked=False):
        mail = SimpleNamespace(id=1, state=state, federation_notification_owned=owned,
                               invalidate_recordset=lambda: None)
        deleted = []
        mail.unlink = lambda: deleted.append(1)
        class Env(dict):
            cr = SimpleNamespace(execute=lambda *args: None, fetchone=lambda: None if locked else (1,))
        env = Env({"federation.notification.log": SimpleNamespace(sudo=lambda: log_model, search_count=lambda domain: logs),
                   "federation.communication.delivery": SimpleNamespace(sudo=lambda: delivery_model, search_count=lambda domain: deliveries)})
        log_model = env["federation.notification.log"]
        delivery_model = env["federation.communication.delivery"]
        rows = Records([mail]); rows.env = env
        count = method("_purge_notification_orphans")(rows)
        return count, deleted

    def test_owned_terminal_orphan_is_deleted(self):
        self.assertEqual(self.run_cleanup(), (1, [1]))

    def test_unrelated_mail_is_kept(self):
        self.assertEqual(self.run_cleanup(owned=False), (0, []))

    def test_pending_and_failed_mail_are_kept(self):
        for state in ("outgoing", "exception"):
            self.assertEqual(self.run_cleanup(state=state), (0, []))

    def test_shared_log_keeps_mail(self):
        self.assertEqual(self.run_cleanup(logs=1), (0, []))

    def test_shared_delivery_keeps_mail(self):
        self.assertEqual(self.run_cleanup(deliveries=1), (0, []))

    def test_busy_mail_is_skipped(self):
        self.assertEqual(self.run_cleanup(locked=True), (0, []))


class TestWiring(unittest.TestCase):
    def test_legacy_rule_is_recipient_scoped(self):
        xml = ElementTree.parse(ROOT / "sports_federation_notifications/security/communication_rules.xml")
        rule = next(node for node in xml.iter("record") if node.attrib.get("id") == "communication_log_visibility")
        text = next(node.text for node in rule if node.attrib.get("name") == "domain_force")
        self.assertIn('[("recipient_partner_id", "=", user.partner_id.id)]', text)
        self.assertNotIn('("target_model", "!=",', text)

    def test_publication_menu_has_one_authoritative_assignment(self):
        xml = ElementTree.parse(ROOT / "sports_federation_navigation/views/navigation.xml")
        records = [node for node in xml.iter("record") if node.attrib.get("id") == "sports_federation_base.menu_federation_publication"]
        self.assertEqual(len(records), 1)
        groups = next(node.attrib["eval"] for node in records[0] if node.attrib.get("name") == "group_ids")
        self.assertIn("group_federation_manager", groups)
        self.assertIn("group_schedule_approver", groups)

    def test_business_writes_are_not_decorated_as_notification_effects(self):
        tree = ast.parse((ROOT / (MODELS + "communication_triggers.py")).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "write":
                self.assertEqual(node.decorator_list, [])
                self.assertTrue(any(isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                                    and call.func.attr == "_run_notification_effect" for call in ast.walk(node)))


if __name__ == "__main__":
    unittest.main()
