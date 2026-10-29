"""Synthetic evidence fixtures test the gate, not product behavior or real novice sessions."""
import copy
from pathlib import Path
import tempfile
import unittest
from verify_role_journeys import validate, load, SPEC, digest, requirements

class JourneyGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'tests.log').write_text('Synthetic gate fixture, not application evidence.')
        self.spec = load(SPEC)
        self.report = {'commit': 'candidate', 'status': 'passed', 'spec_sha256': digest(SPEC),
                       'checks': {k: {'status': 'passed', 'test_id': 'Synthetic.test_gate', 'tests_executed': 1, 'exit_code': 0,
                                      'evidence': [{'path': 'tests.log', 'sha256': digest(self.root / 'tests.log')}]} for k in requirements(self.spec)},
                       'novice_observations': [{'participant_code': 'synthetic_' + str(i), 'task': t, 'completed': True,
                                               'facilitator_interventions': 0, 'elapsed_seconds': 10, 'critical_incidents': 0}
                                              for t in self.spec['novice_tasks'] for i in range(5)]}
    def errors(self): return validate(self.spec, self.report, self.root, 'candidate')
    def test_complete_fixture(self): self.assertEqual(self.errors(), [])
    def test_wrong_commit(self):
        self.report['commit'] = 'old'; self.assertTrue(self.errors())
    def test_missing_check(self):
        self.report['checks'].pop(next(iter(self.report['checks']))); self.assertTrue(self.errors())
    def test_skipped_check(self):
        next(iter(self.report['checks'].values()))['status'] = 'skipped'; self.assertTrue(self.errors())
    def test_zero_tests(self):
        next(iter(self.report['checks'].values()))['tests_executed'] = 0; self.assertTrue(self.errors())
    def test_nonzero_exit(self):
        next(iter(self.report['checks'].values()))['exit_code'] = 1; self.assertTrue(self.errors())
    def test_changed_artifact(self):
        (self.root / 'tests.log').write_text('Changed'); self.assertTrue(self.errors())
    def test_path_escape(self):
        next(iter(self.report['checks'].values()))['evidence'][0]['path'] = '../escape'; self.assertTrue(self.errors())
    def test_no_novice_sessions(self):
        self.report['novice_observations'] = []; self.assertTrue(self.errors())
    def test_insufficient_participants(self):
        self.report['novice_observations'] = [r for r in self.report['novice_observations'] if r['participant_code'] != 'synthetic_4']; self.assertTrue(self.errors())
    def test_duplicate_observation(self):
        self.report['novice_observations'].append(copy.deepcopy(self.report['novice_observations'][0])); self.assertTrue(self.errors())
    def test_critical_incident(self):
        self.report['novice_observations'][0]['critical_incidents'] = 1; self.assertTrue(self.errors())
    def test_intervention_threshold(self):
        self.report['novice_observations'][0]['facilitator_interventions'] = 1
        self.report['novice_observations'][1]['facilitator_interventions'] = 1
        self.assertTrue(self.errors())
    def test_invalid_participant_code(self):
        self.report['novice_observations'][0]['participant_code'] = []
        self.assertTrue(self.errors())
    def test_invalid_elapsed_time(self):
        self.report['novice_observations'][0]['elapsed_seconds'] = float('nan')
        self.assertTrue(self.errors())
    def test_spec_changed(self):
        self.report['spec_sha256'] = 'changed'; self.assertTrue(self.errors())

if __name__ == '__main__': unittest.main()
