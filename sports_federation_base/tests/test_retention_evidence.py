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

    def test_record_execution_keeps_complete_policy_evidence(self):
        from datetime import timedelta

        from odoo import fields

        policy = self.env["federation.retention.policy"].create(
            {
                "name": "Evidence completeness",
                "code": "evidence-completeness",
                "source_model": "res.partner",
                "policy_version": "2026.09",
            }
        )
        evidence = self.env["federation.retention.evidence"].record_execution(
            policy.code,
            started_on=fields.Datetime.now() - timedelta(seconds=5),
            candidate_count=11,
            deleted_count=7,
            skipped_count=4,
            attachment_count=3,
            dry_run=True,
            retention_rules={"terminal_states": ["done"]},
            correlation_id="retention-regression",
        )
        self.assertEqual(evidence.policy_version, "2026.09")
        self.assertEqual(evidence.source_model, "res.partner")
        self.assertEqual((evidence.candidate_count, evidence.deleted_count), (11, 7))
        self.assertEqual((evidence.skipped_count, evidence.attachment_count), (4, 3))
        self.assertTrue(evidence.dry_run)
        self.assertEqual(evidence.correlation_id, "retention-regression")
        self.assertGreaterEqual(evidence.duration_seconds, 5)

    def test_policy_health_distinguishes_never_run_and_latest_failure(self):
        from datetime import timedelta

        from odoo import fields

        policy = self.env["federation.retention.policy"].create(
            {
                "name": "Health regression",
                "code": "health-regression",
                "source_model": "res.partner",
                "expected_interval_hours": 24,
            }
        )
        self.assertEqual(policy.health, "never_run")
        evidence = self.env["federation.retention.evidence"].record_execution(
            policy.code,
            started_on=fields.Datetime.now() - timedelta(seconds=1),
            status="failed",
            failure_count=1,
        )
        policy.invalidate_recordset()
        self.assertEqual(policy.latest_evidence_id, evidence)
        self.assertEqual(policy.health, "attention")
