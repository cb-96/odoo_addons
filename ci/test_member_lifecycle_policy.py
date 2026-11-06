import importlib.util
from pathlib import Path
import unittest
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('member_policy', ROOT / 'sports_federation_member_services/lifecycle_policy.py')
policy = importlib.util.module_from_spec(spec); spec.loader.exec_module(policy)
spec2 = importlib.util.spec_from_file_location('member_acceptance', Path(__file__).with_name('evaluate_member_lifecycle.py'))
acceptance = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(acceptance)


class MemberPolicyTests(unittest.TestCase):
    def test_normal_name(self): self.assertEqual(policy.normal_name('  Jane   DOE '), 'jane doe')
    def test_unicode_normalisation(self): self.assertEqual(policy.normal_name('ＪＡＮＥ'), 'jane')
    def test_match_requires_date(self): self.assertFalse(policy.match_candidate('Jane', 'Doe', None, {'first_name': 'Jane', 'last_name': 'Doe'}))
    def test_exact_matching(self): self.assertTrue(policy.match_candidate('Jane', 'Doe', '2000-01-01', {'first_name': ' JANE ', 'last_name': 'doe', 'birthdate': '2000-01-01'}))
    def test_date_mismatch(self): self.assertFalse(policy.match_candidate('Jane', 'Doe', '2000-01-01', {'first_name': 'Jane', 'last_name': 'Doe', 'birthdate': '2001-01-01'}))
    def test_email_does_not_match(self): self.assertFalse(policy.match_candidate('Jane', 'Doe', '2000-01-01', {'email': 'same@example.test'}))
    def test_draft_label_not_active(self): self.assertIn('review', policy.membership_label('draft'))
    def test_fingerprint_order_stable(self): self.assertEqual(policy.fingerprint({'a': 1, 'b': 2}), policy.fingerprint({'b': 2, 'a': 1}))
    def test_revision_changes_signature(self): self.assertNotEqual(policy.fingerprint(('active', 1)), policy.fingerprint(('active', 2)))
    def licence(self, **values): return dict(state='active', club_id=1, season_id=2, issue_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31), **values)
    def test_valid_licence(self): self.assertTrue(policy.licence_valid(self.licence(), date(2026, 6, 1), 1, 2))
    def test_wrong_club(self): self.assertFalse(policy.licence_valid(self.licence(), date(2026, 6, 1), 3, 2))
    def test_wrong_season(self): self.assertFalse(policy.licence_valid(self.licence(), date(2026, 6, 1), 1, 3))
    def test_expired(self): self.assertFalse(policy.licence_valid(self.licence(), date(2027, 1, 1), 1, 2))
    def test_draft_not_eligible(self):
        licence = self.licence(); licence['state'] = 'draft'
        self.assertFalse(policy.licence_valid(licence, date(2026, 6, 1), 1, 2))
    def test_missing_acceptance_fails(self): self.assertFalse(acceptance.evaluate({})['passed'])
    def fixture(self):
        return {'users': [{'participant': str(i), 'completed': True, 'assisted': False, 'membership_vs_eligibility_correct': True, 'wrong_person_actions': 0} for i in range(10)],
                'routine_renewals': [{'baseline_completed': True, 'candidate_completed': True, 'baseline_touches': 4, 'candidate_touches': 2} for _ in range(10)],
                'adversarial': {name: {'executed': 1, 'wrong_person_actions': 0, 'stale_approvals': 0, 'unauthorised_document_access': 0, 'duplicate_identities': 0} for name in acceptance.REQUIRED}}
    def test_threshold_fixture(self): self.assertTrue(acceptance.evaluate(self.fixture())['passed'])
    def test_duplicate_participant_fails(self):
        data = self.fixture(); data['users'][1]['participant'] = '0'; self.assertFalse(acceptance.evaluate(data)['passed'])
    def test_wrong_person_fails(self):
        data = self.fixture(); data['adversarial']['two_dependants']['wrong_person_actions'] = 1; self.assertFalse(acceptance.evaluate(data)['passed'])
    def test_stale_approval_fails(self):
        data = self.fixture(); data['adversarial']['stale_document']['stale_approvals'] = 1; self.assertFalse(acceptance.evaluate(data)['passed'])
    def test_duplicate_identity_fails(self):
        data = self.fixture(); data['adversarial']['concurrent_matching']['duplicate_identities'] = 1; self.assertFalse(acceptance.evaluate(data)['passed'])
    def test_missing_concurrency_fails(self):
        data = self.fixture(); del data['adversarial']['concurrent_renewal']; self.assertFalse(acceptance.evaluate(data)['passed'])
    def test_insufficient_touch_reduction_fails(self):
        data = self.fixture()
        for row in data['routine_renewals']: row['candidate_touches'] = 3
        self.assertFalse(acceptance.evaluate(data)['passed'])


if __name__ == '__main__': unittest.main()
