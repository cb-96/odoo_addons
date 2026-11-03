"""Presentation regression tests. No Odoo runtime or human evidence implied."""
from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import unittest
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cards', ROOT / 'sports_federation_portal/journey_cards.py')
cards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cards)


class ConnectedPolicyTests(unittest.TestCase):
    def test_single_role_default(self):
        for role in cards.ROLE_ORDER:
            self.assertEqual(cards.choose_role([role]), role)

    def test_remembered_role(self):
        self.assertEqual(cards.choose_role(['club', 'reviewer'], remembered='reviewer'), 'reviewer')

    def test_explicit_switch(self):
        self.assertEqual(cards.choose_role(['club', 'reviewer'], 'club', 'reviewer'), 'club')

    def test_revoked_role(self):
        self.assertEqual(cards.choose_role(['club'], remembered='manager'), 'club')

    def test_no_access(self):
        self.assertIsNone(cards.choose_role([], 'manager', 'manager'))

    def test_complete_precedence(self):
        self.assertEqual(cards.bucket_for(complete=True, waiting=True, blocking=True), 'recent')

    def test_waiting_precedence(self):
        self.assertEqual(cards.bucket_for(waiting=True, blocking=True), 'waiting')

    def test_unavailable_never_actionable(self):
        self.assertEqual(cards.bucket_for(unavailable=True), 'waiting')

    def test_deadline_boundaries(self):
        now = datetime(2026, 11, 2)
        for days, expected in [(-1, 'now'), (0, 'now'), (1, 'soon'), (7, 'soon'), (8, 'now')]:
            self.assertEqual(cards.bucket_for(deadline=now + timedelta(days=days), now=now), expected)

    def test_blocker_is_action_now(self):
        now = datetime(2026, 11, 2)
        self.assertEqual(cards.bucket_for(deadline=now + timedelta(days=1), now=now, blocking=True), 'now')

    def test_no_deadline(self):
        self.assertEqual(cards.bucket_for(), 'now')

    def test_deduplication(self):
        groups = cards.group_cards([{'key': 'a', 'bucket': 'now'}, {'key': 'a', 'bucket': 'now'}])
        self.assertEqual(len(groups['now']), 1)
        self.assertEqual(list(groups), list(cards.BUCKETS))

    def test_empty_summary_not_ready(self):
        self.assertEqual(cards.participation_status([]), 'unknown')

    def test_summary_precedence(self):
        for states, expected in [(['complete'], 'complete'), (['complete', 'unknown'], 'unknown'),
                                 (['unknown', 'waiting'], 'waiting'), (['waiting', 'action'], 'action')]:
            self.assertEqual(cards.participation_status([{'state': s} for s in states]), expected)

    def test_shared_card_metadata(self):
        tree = etree.parse(str(ROOT / 'sports_federation_portal/views/role_journey_templates.xml'))
        template = tree.xpath('//template[@id="connected_work_card"]')[0]
        text = etree.tostring(template, encoding='unicode')
        for field in ('owner', 'deadline', 'blocker', 'next_action', 'handoff'):
            self.assertIn("card['%s']" % field, text)
        self.assertTrue(template.xpath('.//form[@action="/my/action-items/assign"]'))

    def test_local_inheritance_selectors(self):
        tree = etree.parse(str(ROOT / 'sports_federation_portal/views/role_journey_templates.xml'))
        parent = etree.parse(str(ROOT / 'sports_federation_portal/views/portal_templates.xml'))
        def hasclass(context, *names):
            return all(name in context.context_node.get('class', '').split() for name in names)
        for xpath in tree.xpath('//template[@id="inbox_journey"]/xpath'):
            self.assertTrue(parent.xpath(xpath.get('expr'), extensions={(None, 'hasclass'): hasclass}), xpath.get('expr'))


if __name__ == '__main__':
    unittest.main()
