from odoo.tests import TransactionCase


class TestReportScheduleCron(TransactionCase):
    """Tests for the federation.report.schedule generation logic."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create({
            "name": "Cron Test Season",
            "date_start": "2024-09-01",
            "date_end": "2025-06-30",
        })

    def _make_schedule(self, report_type, period_type="weekly", **kwargs):
        vals = {
            "name": f"Test {report_type}",
            "report_type": report_type,
            "period_type": period_type,
            "next_run_on": "2024-10-01 00:00:00",
        }
        vals.update(kwargs)
        return self.env["federation.report.schedule"].create(vals)

    def test_generate_operational_report_succeeds(self):
        schedule = self._make_schedule("operational", season_id=self.season.id)
        schedule._generate_single_report()
        self.assertEqual(schedule.last_run_status, "success")
        self.assertTrue(schedule.generated_file)

    def test_generate_standing_reconciliation_report_succeeds(self):
        schedule = self._make_schedule(
            "standing_reconciliation", season_id=self.season.id
        )
        schedule._generate_single_report()
        self.assertEqual(schedule.last_run_status, "success")
        self.assertTrue(schedule.generated_file)

    def test_generate_finance_reconciliation_report_succeeds(self):
        schedule = self._make_schedule("finance_reconciliation")
        schedule._generate_single_report()
        self.assertEqual(schedule.last_run_status, "success")
        self.assertTrue(schedule.generated_file)

    def test_generated_file_has_nonzero_bytes(self):
        import base64
        schedule = self._make_schedule("operational", season_id=self.season.id)
        schedule._generate_single_report()
        data = base64.b64decode(schedule.generated_file)
        self.assertGreater(len(data), 0)

    def test_failure_in_one_report_does_not_affect_another(self):
        """A bad schedule that fails should record failure without crashing others."""
        good = self._make_schedule("operational", season_id=self.season.id)
        # Simulate a bad schedule by temporarily monkeypatching the builder
        bad = self._make_schedule("operational", name="Bad Schedule")
        original_build = type(bad)._build_report_payload

        def _broken_build(self_inner):
            raise RuntimeError("Simulated builder failure")

        try:
            type(bad)._build_report_payload = _broken_build
            bad._generate_single_report()
        finally:
            type(bad)._build_report_payload = original_build

        self.assertEqual(bad.last_run_status, "failed")
        self.assertGreater(bad.consecutive_failure_count, 0)
        # Good schedule is untouched
        good._generate_single_report()
        self.assertEqual(good.last_run_status, "success")

    def test_last_run_on_is_set_after_success(self):
        schedule = self._make_schedule("operational", season_id=self.season.id)
        self.assertFalse(schedule.last_run_on)
        schedule._generate_single_report()
        self.assertTrue(schedule.last_run_on)
