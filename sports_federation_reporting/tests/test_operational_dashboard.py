from odoo import fields
from odoo.tests import TransactionCase


class TestOperationalDashboard(TransactionCase):
    def test_snapshot_aggregates_source_queues_without_persisting_copies(self):
        self.env["federation.operation.job"].create({"name": "Dashboard retry", "source_model": "federation.report.schedule", "source_res_id": 42, "correlation_id": "dashboard-retry", "state": "retry", "next_retry_on": fields.Datetime.now()})
        values = self.env["federation.operational.dashboard"]._snapshot_values()
        self.assertGreaterEqual(values["retrying_job_count"], 1)
        self.assertEqual(values["overall_status"], "attention")

    def test_dashboard_links_preserve_source_ownership(self):
        Dashboard = self.env["federation.operational.dashboard"]
        dashboard = Dashboard.create(Dashboard._snapshot_values())
        action = dashboard.action_open_reviews()
        self.assertEqual(action["res_model"], "federation.schedule.review")
        self.assertEqual(action["domain"], [("state", "=", "pending")])

    def test_failed_release_evidence_blocks_readiness(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("sports_federation.release.last_status", "failed")
        params.set_param("sports_federation.release.last_sha", "deadbeef")
        values = self.env["federation.operational.dashboard"]._snapshot_values()
        self.assertEqual(values["release_status"], "failed")
        self.assertEqual(values["release_candidate_sha"], "deadbeef")
        self.assertEqual(values["overall_status"], "blocked")
