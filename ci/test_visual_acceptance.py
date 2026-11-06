"""Unit fixtures exercise gates; these are not measured usability observations."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('visual_acceptance', Path(__file__).with_name('evaluate_visual_scheduling.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AcceptanceTests(unittest.TestCase):
    def fixture(self):
        return {'novices': [{'participant': str(i), 'completed': True, 'assisted': False,
                            'hard_vs_preference_correct': True, 'affected_fixtures_correct': True} for i in range(10)],
                'paired_timings': [{'participant': str(i), 'baseline_completed': True, 'candidate_completed': True,
                                   'baseline_seconds': 100, 'candidate_seconds': 70} for i in range(10)],
                'integrity': {name: {'executed': 1, 'accepted_hard_violations': 0, 'unintended_pin_changes': 0} for name in module.REQUIRED}}

    def test_missing_evidence_fails(self):
        self.assertFalse(module.evaluate({})['passed'])

    def test_threshold_fixture(self):
        data = self.fixture()
        for row in data['novices'][:2]: row['completed'] = False
        data['novices'][0]['hard_vs_preference_correct'] = False
        data['novices'][0]['affected_fixtures_correct'] = False
        self.assertTrue(module.evaluate(data)['passed'])

    def test_duplicate_participant_fails(self):
        data = self.fixture(); data['novices'][1]['participant'] = '0'
        self.assertFalse(module.evaluate(data)['passed'])

    def test_one_hard_violation_fails(self):
        data = self.fixture(); data['integrity']['team_overlap']['accepted_hard_violations'] = 1
        self.assertFalse(module.evaluate(data)['passed'])

    def test_one_pin_change_fails(self):
        data = self.fixture(); data['integrity']['pinned_regeneration']['unintended_pin_changes'] = 1
        self.assertFalse(module.evaluate(data)['passed'])

    def test_missing_suite_case_fails(self):
        data = self.fixture(); del data['integrity']['mandatory_rest']
        self.assertFalse(module.evaluate(data)['passed'])

    def test_infinite_time_fails(self):
        data = self.fixture(); data['paired_timings'][0]['baseline_seconds'] = float('inf')
        self.assertFalse(module.evaluate(data)['passed'])

    def test_less_than_30_percent_fails(self):
        data = self.fixture()
        for row in data['paired_timings']: row['candidate_seconds'] = 71
        self.assertFalse(module.evaluate(data)['passed'])


if __name__ == '__main__': unittest.main()
