import datetime as dt
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_test_date_horizon", Path(__file__).with_name("check_test_date_horizon.py")
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class TestDateHorizonTests(unittest.TestCase):
    def tree(self, source):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        tests = root / "sports_federation_x" / "tests"
        tests.mkdir(parents=True)
        (tests / "test_x.py").write_text(source)
        return root

    def run_check(self, root, baseline=None, today=dt.date(2026, 11, 20)):
        return checker.check(root, baseline or {}, today)

    def test_expiring_dates_are_reported(self):
        root = self.tree('a = "2027-03-01"\nb = "2027-04-01 18:00:00"\n')
        errors, _warnings, found = self.run_check(root)
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(found["sports_federation_x/tests/test_x.py"]), 2)

    def test_past_far_future_and_exempt_dates_are_fine(self):
        root = self.tree(
            'a = "2025-06-01"\n'
            'b = "2090-01-01"\n'
            'c = "2027-01-01"  # fixed-date: parsing test, never compared to today\n'
        )
        errors, _warnings, found = self.run_check(root)
        self.assertEqual(errors, [])
        self.assertEqual(found, {})

    def test_baseline_allows_existing_but_not_more(self):
        root = self.tree('a = "2027-03-01"\nb = "2027-03-02"\n')
        rel = "sports_federation_x/tests/test_x.py"
        self.assertEqual(self.run_check(root, {rel: 2})[0], [])
        self.assertEqual(len(self.run_check(root, {rel: 1})[0]), 1)

    def test_rule_does_not_change_with_the_calendar(self):
        root = self.tree('a = "2027-03-01"\n')
        rel = "sports_federation_x/tests/test_x.py"
        for today in (dt.date(2026, 12, 1), dt.date(2030, 1, 1)):
            self.assertEqual(self.run_check(root, {rel: 1}, today)[0], [])

    def test_imminent_dates_warn(self):
        root = self.tree('a = "2026-12-01"\n')
        _errors, warnings, _found = self.run_check(
            root, {"sports_federation_x/tests/test_x.py": 1}
        )
        self.assertEqual(len(warnings), 1)

    def test_repository_is_within_its_baseline(self):
        errors, _warnings, _found = checker.check(
            checker.ROOT, checker.load_baseline(checker.BASELINE), dt.date.today()
        )
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
