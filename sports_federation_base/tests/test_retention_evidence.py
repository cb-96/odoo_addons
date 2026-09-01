from odoo.tests.common import TransactionCase


class TestRetentionEvidence(TransactionCase):
    def test_evidence_is_append_only_for_federation_users(self):
        evidence = self.env['federation.retention.evidence'].sudo().create({
            'policy': 'test', 'status': 'passed', 'deleted_count': 3,
        })
        self.assertEqual(evidence.deleted_count, 3)
        manager = self.env.ref('base.user_admin')
        self.assertFalse(self.env['federation.retention.evidence'].with_user(manager).check_access_rights('write', raise_exception=False))
