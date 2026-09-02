from odoo.tests.common import TransactionCase


class TestRetentionEvidence(TransactionCase):
    def test_evidence_acl_is_read_only_for_federation_managers(self):
        evidence = (
            self.env["federation.retention.evidence"]
            .sudo()
            .create({"policy": "test", "status": "passed", "deleted_count": 3})
        )
        self.assertEqual(evidence.deleted_count, 3)

        manager_group = self.env.ref("sports_federation_base.group_federation_manager")
        model = self.env["ir.model"]._get("federation.retention.evidence")
        access = self.env["ir.model.access"].search(
            [
                ("group_id", "=", manager_group.id),
                ("model_id", "=", model.id),
            ]
        )
        self.assertTrue(access)
        self.assertTrue(any(access.mapped("perm_read")))
        self.assertFalse(any(access.mapped("perm_write")))
        self.assertFalse(any(access.mapped("perm_create")))
        self.assertFalse(any(access.mapped("perm_unlink")))
