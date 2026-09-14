import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("check_repo.py")
SPEC = importlib.util.spec_from_file_location("check_repo", MODULE_PATH)
CHECK_REPO = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECK_REPO
SPEC.loader.exec_module(CHECK_REPO)


class CheckRepoTest(unittest.TestCase):
    def test_categories_are_small_and_unique(self):
        all_checks = [check for checks in CHECK_REPO.CHECKS.values() for check in checks]
        self.assertEqual(len(all_checks), len(set(all_checks)))
        self.assertEqual(
            set(CHECK_REPO.CHECKS),
            {"integrity", "security", "workflows", "compatibility", "release"},
        )

    def test_referenced_checks_use_repository_paths(self):
        for checks in CHECK_REPO.CHECKS.values():
            for check in checks:
                self.assertTrue(check.startswith("ci/check_"))
                self.assertTrue(check.endswith(".py"))


if __name__ == "__main__":
    unittest.main()
