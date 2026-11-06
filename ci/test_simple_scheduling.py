import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "simple_status", ROOT / "sports_federation_scheduling/simple_status.py"
)
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


class MessageTests(unittest.TestCase):
    def test_repeated_messages_collapse_with_a_count(self):
        items = [{"message": "Slot taken"}] * 3 + [{"message": "No court"}]
        self.assertEqual(
            status.group_messages(items, "x"), ["Slot taken (x3)", "No court"]
        )

    def test_missing_message_falls_back_to_code_then_text(self):
        self.assertEqual(status.group_messages([{"code": "scope"}], "x"), ["scope"])
        self.assertEqual(
            status.group_messages([{}], "Schedule conflict"), ["Schedule conflict"]
        )

    def test_errors_and_warnings_never_mix(self):
        must, could = status.split_validation(
            {
                "errors": [{"message": "Hard"}],
                "warnings": [{"message": "Soft"}],
                "unassigned_fixture_ids": [],
            }
        )
        self.assertEqual(must, ["Hard"])
        self.assertEqual(could, ["Soft"])

    def test_unassigned_matches_are_must_fix(self):
        must, could = status.split_validation({"unassigned_fixture_ids": [1, 2]})
        self.assertEqual(must, ["2 matches still need a court and time."])
        self.assertEqual(could, [])
        must, _could = status.split_validation({"unassigned_fixture_ids": [1]})
        self.assertEqual(must, ["1 match still needs a court and time."])

    def test_counts_include_unassigned(self):
        self.assertEqual(
            status.counts(
                {
                    "errors": [{}, {}],
                    "warnings": [{}],
                    "unassigned_fixture_ids": [1, 2, 3],
                }
            ),
            (5, 1),
        )

    def test_summary_matches_the_default_screen(self):
        self.assertEqual(
            status.summary(24, 2, 0),
            "24 matches scheduled \u00b7 2 preference warnings \u00b7 0 blocking conflicts",
        )
        self.assertEqual(
            status.summary(1, 1, 1),
            "1 match scheduled \u00b7 1 preference warning \u00b7 1 blocking conflict",
        )

    def test_empty_validation_is_clean(self):
        self.assertEqual(status.split_validation({}), ([], []))
        self.assertEqual(status.counts({}), (0, 0))


class ContractTests(unittest.TestCase):
    def test_repository_honours_the_simple_scheduling_contract(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "ci/check_simple_scheduling.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
