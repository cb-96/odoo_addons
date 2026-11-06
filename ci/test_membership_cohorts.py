import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('cohorts', Path(__file__).resolve().parents[1] / 'sports_federation_member_services/cohorts.py')
cohorts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cohorts)


class TestCohorts(unittest.TestCase):
    def test_empty_baseline_is_unknown(self):
        self.assertIsNone(cohorts.compare_cohorts([], [1])['retention_percent'])

    def test_multiple_roles_do_not_duplicate_people(self):
        self.assertEqual(cohorts.compare_cohorts([1, 1, 2], [1, 1, 3])['returning'], 1)

    def test_leavers_and_new_members(self):
        result = cohorts.compare_cohorts([1, 2], [2, 3])
        self.assertEqual((result['new'], result['not_returned'], result['retention_percent']), (1, 1, 50.0))

    def test_no_returners(self):
        self.assertEqual(cohorts.compare_cohorts([1], [])['retention_percent'], 0)

    def test_all_returners(self):
        self.assertEqual(cohorts.compare_cohorts([1, 2], [2, 1])['retention_percent'], 100)
