from unittest.mock import patch

from odoo.tests import TransactionCase


class TestReportSnapshot(TransactionCase):
    def test_compliance_pending_total_uses_single_aggregate_query(self):
        snapshot_model = self.env["federation.report.snapshot"]

        with patch.object(
            snapshot_model.env.cr, "execute"
        ) as execute_mock, patch.object(
            snapshot_model.env.cr,
            "fetchone",
            return_value=(11,),
        ) as fetchone_mock:
            total = snapshot_model._compliance_pending_total()

        self.assertEqual(total, 11)
        self.assertEqual(execute_mock.call_count, 1)
        self.assertEqual(fetchone_mock.call_count, 1)

    def test_capture_snapshot_produces_expected_rows(self):
        records = self.env["federation.report.snapshot"].capture_snapshot()

        self.assertTrue(records)
        self.assertEqual(len(records), 5)
        self.assertTrue(all(record.snapshot_type for record in records))
