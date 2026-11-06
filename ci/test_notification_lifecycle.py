"""Pure tests for the actionable-notification lifecycle."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "communication_policy", ROOT / "sports_federation_notifications/communication_policy.py"
)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
state = policy.lifecycle_state


class LifecycleTests(unittest.TestCase):
    def test_all_eight_states_exist(self):
        self.assertEqual(
            [code for code, _label in policy.LIFECYCLE],
            ["created", "queued", "delivered", "failed", "seen", "acted", "expired", "superseded"],
        )

    def test_nothing_recorded_is_created(self):
        self.assertEqual(state(), "created")
        self.assertEqual(state(delivery_states=["cancelled"]), "created")

    def test_delivery_progress(self):
        self.assertEqual(state(delivery_states=["pending"]), "queued")
        self.assertEqual(state(delivery_states=["queued"]), "queued")
        self.assertEqual(state(delivery_states=["sent"]), "delivered")
        self.assertEqual(state(delivery_states=["suppressed"]), "delivered")
        self.assertEqual(state(delivery_states=["failed"]), "failed")

    def test_one_accepted_delivery_beats_a_failed_attempt(self):
        self.assertEqual(state(delivery_states=["failed", "sent"]), "delivered")

    def test_seen_beats_delivery_and_failure(self):
        self.assertEqual(state(seen=True, delivery_states=["sent"]), "seen")
        self.assertEqual(state(seen=True, delivery_states=["failed"]), "seen")

    def test_precedence_of_the_closing_states(self):
        self.assertEqual(state(acted=True, expired=True, seen=True), "acted")
        self.assertEqual(state(expired=True, seen=True), "expired")
        self.assertEqual(state(superseded=True, acted=True, expired=True), "superseded")

    def test_seen_is_never_acted_upon(self):
        self.assertNotEqual(state(seen=True, delivery_states=["sent"]), "acted")

    def test_closed_states_are_terminal_in_the_policy(self):
        self.assertEqual(set(policy.CLOSED_LIFECYCLE), {"acted", "expired", "superseded"})


class ReportTests(unittest.TestCase):
    def test_resolution_rate_counts_only_finished_or_stalled_items(self):
        report = policy.summarize_lifecycle(
            [
                ("due_soon", "acted", 6),
                ("due_soon", "expired", 2),
                ("due_soon", "seen", 2),
                ("due_soon", "queued", 40),
            ]
        )
        self.assertEqual(report["resolution_rate"], 0.6)
        self.assertEqual(report["seen_unresolved"], 2)
        self.assertEqual(report["totals"]["queued"], 40)

    def test_no_finished_items_means_no_rate(self):
        self.assertIsNone(policy.summarize_lifecycle([("due_soon", "queued", 3)])["resolution_rate"])
        self.assertIsNone(policy.summarize_lifecycle([])["resolution_rate"])

    def test_kinds_are_kept_apart(self):
        report = policy.summarize_lifecycle(
            [("due_soon", "acted", 1), ("schedule_change", "seen", 4)]
        )
        self.assertEqual(report["by_kind"]["due_soon"], {"acted": 1})
        self.assertEqual(report["by_kind"]["schedule_change"], {"seen": 4})


if __name__ == "__main__":
    unittest.main()
