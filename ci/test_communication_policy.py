"""Run without Odoo: python -m unittest discover -s ci -p test_communication_policy.py."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('communication_policy', ROOT / 'sports_federation_notifications/communication_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class CommunicationPolicyTests(unittest.TestCase):
    def test_replay_identity_stable(self):
        self.assertEqual(policy.identity('event', 10), policy.identity('event', 10))

    def test_distinct_recipients(self):
        self.assertNotEqual(policy.identity('event', 10), policy.identity('event', 11))

    def test_distinct_events(self):
        self.assertNotEqual(policy.identity('event', 10), policy.identity('changed', 10))

    def test_overlap_roles_deduplicate(self):
        self.assertEqual(policy.merge_roles([(10, 'club'), (10, 'official'), (10, 'club')]), {10: ['club', 'official']})

    def test_empty_routes(self):
        self.assertEqual(policy.merge_roles([]), {})

    def test_role_order_is_stable(self):
        self.assertEqual(policy.merge_roles([(10, 'official'), (10, 'club')]), policy.merge_roles([(10, 'club'), (10, 'official')]))

    def test_backoff_increases(self):
        self.assertLess(policy.retry_delay(1), policy.retry_delay(2))

    def test_backoff_bounded(self):
        self.assertEqual(policy.retry_delay(100), 60)

    def test_sent_is_not_read_or_complete(self):
        label = policy.delivery_label('sent').lower()
        self.assertIn('mail server', label)
        self.assertNotIn('completed', label)
        self.assertNotIn('read', label)

    def test_queued_is_not_sent(self):
        self.assertEqual(policy.delivery_label('queued'), 'Queued for email')

    def test_identity_many_roles_and_replays(self):
        routes = [(user, role) for user in range(10) for role in ('club', 'team', 'official') for _ in range(5)]
        self.assertEqual(len(policy.merge_roles(routes)), 10)
        self.assertEqual(len({policy.identity('same-event', user) for user, role in routes}), 10)

    def test_unknown_state_is_not_success(self):
        self.assertEqual(policy.delivery_label('unknown'), 'Not checked')
