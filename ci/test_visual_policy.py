import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('visual_policy', ROOT / 'sports_federation_live_workspace/visual_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class VisualPolicyTests(unittest.TestCase):
    def test_empty_closure(self):
        self.assertEqual(policy.closure([], {}), [])

    def test_transitive_fixture_dependency(self):
        self.assertEqual(policy.closure([1], {1: [2], 2: [3]}), [2, 3])

    def test_cycle_safe(self):
        self.assertEqual(policy.closure([1], {1: [2], 2: [1]}), [2])

    def test_multiple_roots_excluded(self):
        self.assertEqual(policy.closure([1, 2], {1: [2], 2: [3]}), [3])

    def test_no_duplicate_descendants(self):
        self.assertEqual(policy.closure([1], {1: [2, 3], 2: [4], 3: [4]}), [2, 3, 4])

    def test_shared_team_is_review_not_move(self):
        fixtures = [{'id': 1, 'stage_id': 10, 'teams': [7]}, {'id': 2, 'stage_id': 10, 'teams': [7]}]
        impact = policy.impact_sets([1], fixtures, [])
        self.assertEqual(impact['changed'], [1])
        self.assertEqual(impact['shared_teams'], [2])

    def test_fixture_and_stage_dependencies_separate(self):
        fixtures = [{'id': 1, 'stage_id': 10}, {'id': 2, 'stage_id': 20, 'home_source': 1}, {'id': 3, 'stage_id': 20}]
        impact = policy.impact_sets([1], fixtures, [{'id': 10, 'next': [{'id': 20}]}])
        self.assertEqual(impact['fixture_dependants'], [2])
        self.assertEqual(impact['stage_dependants'], [2, 3])

    def test_unrelated_division_not_impacted(self):
        fixtures = [{'id': 1, 'stage_id': 10}, {'id': 2, 'stage_id': 99}]
        self.assertEqual(policy.impact_sets([1], fixtures, [])['stage_dependants'], [])

    def test_no_changes_no_impact(self):
        self.assertTrue(all(not ids for ids in policy.impact_sets([], [{'id': 1, 'stage_id': 10}], []).values()))

    def test_manual_pin_preserved(self):
        self.assertEqual(policy.pin_changes({1: 10}, {1: 10}, {1: 'manual'}), [])

    def test_manual_pin_move_detected(self):
        self.assertEqual(policy.pin_changes({1: 10}, {1: 11}, {1: 'manual'}), [1])

    def test_operational_pin_removal_detected(self):
        self.assertEqual(policy.pin_changes({1: 10}, {}, {1: 'operational'}), [1])

    def test_automatic_can_change(self):
        self.assertEqual(policy.pin_changes({1: 10}, {1: 11}, {1: 'automatic'}), [])

    def test_input_maps_not_mutated(self):
        before, after = {1: 10}, {1: 11}
        policy.pin_changes(before, after, {1: 'manual'})
        self.assertEqual(before, {1: 10}); self.assertEqual(after, {1: 11})


if __name__ == '__main__':
    unittest.main()
