import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vocabulary = load("sports_federation_base/readiness_vocabulary.py", "vocabulary")
cards = load("sports_federation_portal/journey_cards.py", "journey_cards")
member_policy = load(
    "sports_federation_member_services/lifecycle_policy.py", "member_policy"
)


class ContractTests(unittest.TestCase):
    def test_repository_honours_the_readiness_contract(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "ci/check_readiness_vocabulary.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class JourneyTests(unittest.TestCase):
    def test_no_checks_is_never_a_certificate(self):
        self.assertEqual(cards.participation_status([]), "unknown")
        self.assertEqual(
            cards.participation_status([{"state": "not_applicable"}]), "unknown"
        )

    def test_a_check_that_does_not_apply_is_left_out(self):
        checks = [{"state": "complete"}, {"state": "not_applicable"}]
        self.assertEqual(cards.participation_status(checks), "complete")

    def test_unknown_still_beats_complete(self):
        checks = [{"state": "complete"}, {"state": "unknown"}]
        self.assertEqual(cards.participation_status(checks), "unknown")

    def test_action_and_waiting_keep_their_priority(self):
        self.assertEqual(
            cards.participation_status(
                [{"state": "waiting"}, {"state": "not_applicable"}, {"state": "action"}]
            ),
            "action",
        )
        self.assertEqual(
            cards.participation_status([{"state": "waiting"}, {"state": "complete"}]),
            "waiting",
        )

    def test_every_journey_state_has_a_shared_status(self):
        for state in ("action", "waiting", "unknown", "complete", "not_applicable"):
            self.assertIn(state, vocabulary.STATE_MAPPINGS["journey"])

    def test_no_game_days_is_not_applicable_not_unknown(self):
        self.assertEqual(
            vocabulary.status_for("journey", "not_applicable"),
            vocabulary.NOT_APPLICABLE,
        )


class WordingTests(unittest.TestCase):
    def test_unrecognised_membership_is_not_called_checked(self):
        label = member_policy.membership_label("mystery")
        self.assertNotIn("Not checked", label)
        self.assertTrue(label.startswith("Action needed"))

    def test_line_up_states_map_to_the_shared_words(self):
        expected = {
            "not_started": "Action needed",
            "draft": "Action needed",
            "submitted": "Waiting for review",
            "approved": "Ready",
            "locked": "Complete",
        }
        for state, label in expected.items():
            self.assertEqual(
                vocabulary.label_for(vocabulary.status_for("lineup", state)), label
            )

    def test_roster_states_map_to_the_shared_words(self):
        expected = {"draft": "Action needed", "active": "Ready", "closed": "Complete"}
        for state, label in expected.items():
            self.assertEqual(
                vocabulary.label_for(vocabulary.status_for("roster", state)), label
            )

    def test_schedule_review_and_publication_are_distinguished(self):
        self.assertEqual(
            vocabulary.status_for("schedule", "ready_for_review"),
            vocabulary.WAITING_REVIEW,
        )
        self.assertEqual(
            vocabulary.status_for("schedule", "approved"), vocabulary.ACTION_NEEDED
        )
        self.assertEqual(
            vocabulary.status_for("schedule", "published"), vocabulary.READY
        )


if __name__ == "__main__":
    unittest.main()
