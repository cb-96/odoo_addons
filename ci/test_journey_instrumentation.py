"""Pure tests for journey instrumentation."""

from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "journey_instrumentation",
    ROOT / "sports_federation_portal/journey_instrumentation.py",
)
instr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(instr)

NOW = datetime(2026, 11, 5, 12, 0)


def event(journey, kind, session, minutes_ago=0, screen=None):
    return {
        "journey": journey,
        "event": kind,
        "session_key": session,
        "screen": screen,
        "occurred_on": NOW - timedelta(minutes=minutes_ago),
    }


class SessionKeyTests(unittest.TestCase):
    def test_key_is_a_stable_hash_not_the_raw_session(self):
        key = instr.session_key("raw-session-id")
        self.assertEqual(key, instr.session_key("raw-session-id"))
        self.assertNotIn("raw-session-id", key)
        self.assertEqual(len(key), 16)
        self.assertNotEqual(key, instr.session_key("another"))


class CountTests(unittest.TestCase):
    def test_counts_per_journey(self):
        result = instr.summarize(
            [
                event("work", "entry", "a", screen="home"),
                event("x.y", "action", "a"),
                event("x.y", "validation_error", "a"),
                event("x.y", "retry", "a"),
            ],
            NOW,
        )
        self.assertEqual(result["by_journey"]["work"]["entries"], 1)
        self.assertEqual(result["by_journey"]["x.y"]["actions"], 1)
        self.assertEqual(result["by_journey"]["x.y"]["validation_errors"], 1)
        self.assertEqual(result["by_journey"]["x.y"]["retries"], 1)

    def test_validation_error_rate(self):
        result = instr.summarize(
            [event("c", "action", "a")] * 3 + [event("c", "validation_error", "a")], NOW
        )
        self.assertEqual(result["by_journey"]["c"]["validation_error_rate"], 0.25)

    def test_no_attempts_means_no_rate(self):
        result = instr.summarize([event("work", "entry", "a")], NOW)
        self.assertIsNone(result["by_journey"]["work"]["validation_error_rate"])

    def test_unknown_event_kinds_are_ignored(self):
        self.assertEqual(
            instr.summarize([event("w", "banana", "a")], NOW)["by_journey"], {}
        )


class SessionTests(unittest.TestCase):
    def test_entered_then_worked_is_not_abandoned(self):
        result = instr.summarize(
            [event("work", "entry", "a", 120), event("x.y", "action", "a", 100)], NOW
        )
        self.assertEqual(result["sessions"]["worked"], 1)
        self.assertEqual(result["sessions"]["abandoned"], 0)

    def test_entered_and_left_is_abandoned_after_the_grace_period(self):
        result = instr.summarize([event("work", "entry", "a", 120)], NOW)
        self.assertEqual(result["sessions"]["abandoned"], 1)
        self.assertEqual(result["sessions"]["abandonment_rate"], 1.0)

    def test_a_recent_entry_is_still_in_progress(self):
        result = instr.summarize([event("work", "entry", "a", 5)], NOW)
        self.assertEqual(result["sessions"]["abandoned"], 0)
        self.assertEqual(result["sessions"]["in_progress"], 1)

    def test_average_screens_and_actions(self):
        events = [
            event("work", "entry", "a", 100, screen="home"),
            event("task", "entry", "a", 99, screen="task_open"),
            event("x.y", "action", "a", 98),
            event("x.y", "action", "a", 97),
            event("work", "entry", "b", 90, screen="home"),
            event("x.y", "action", "b", 89),
        ]
        sessions = instr.summarize(events, NOW)["sessions"]
        self.assertEqual(sessions["avg_screens"], 1.5)
        self.assertEqual(sessions["avg_actions"], 1.5)

    def test_events_without_a_session_do_not_form_sessions(self):
        sessions = instr.summarize([event("work", "entry", None)], NOW)["sessions"]
        self.assertEqual(sessions["entered"], 0)
        self.assertIsNone(sessions["avg_screens"])
        self.assertIsNone(sessions["abandonment_rate"])

    def test_empty_input(self):
        result = instr.summarize([], NOW)
        self.assertEqual(result["by_journey"], {})
        self.assertEqual(result["sessions"]["entered"], 0)


class ContractTests(unittest.TestCase):
    def test_repository_honours_the_instrumentation_contract(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "ci/check_journey_instrumentation.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
