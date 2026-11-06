import unittest
from pathlib import Path
from check_candidate_acceptance import validate, REQUIRED


class TestCandidateAcceptance(unittest.TestCase):
    def test_pending_cannot_pass(self):
        self.assertTrue(
            validate({"commit": "a" * 40, "checks": {}}, "a" * 40, Path("."))
        )

    def test_wrong_commit_cannot_pass(self):
        self.assertTrue(
            any(
                "exact full candidate commit" in error
                for error in validate({"commit": "b" * 40}, "a" * 40, Path("."))
            )
        )

    def test_all_categories_required(self):
        self.assertEqual(len(REQUIRED), 9)


if __name__ == "__main__":
    unittest.main()
