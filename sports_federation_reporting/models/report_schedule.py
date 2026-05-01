import base64
import csv
import io
import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.addons.sports_federation_base.models.failure_feedback import (
    FAILURE_CATEGORY_SELECTION,
    build_failure_feedback,
    get_failure_category_label,
)

from ..services import report_schedule_builders

_logger = logging.getLogger(__name__)


class FederationReportSchedule(models.Model):
    _name = "federation.report.schedule"
    _description = "Federation Report Schedule"
    _order = "next_run_on, name"

    GENERATED_FILE_RETENTION_DAYS = 60

    RUN_STATUS_SELECTION = [
        ("never", "Never Run"),
        ("success", "Last Run Succeeded"),
        ("failed", "Last Run Failed"),
    ]

    REPORT_TYPE_SELECTION = report_schedule_builders.REPORT_TYPE_SELECTION
    PERIOD_TYPE_SELECTION = [
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
    ]

    name = fields.Char(required=True)
    report_type = fields.Selection(
        REPORT_TYPE_SELECTION, required=True, default="operational"
    )
    period_type = fields.Selection(
        PERIOD_TYPE_SELECTION, required=True, default="weekly"
    )
    season_id = fields.Many2one("federation.season", string="Season")
    active = fields.Boolean(default=True)
    next_run_on = fields.Datetime(required=True, default=fields.Datetime.now)
    last_attempt_on = fields.Datetime(readonly=True)
    last_run_on = fields.Datetime(readonly=True)
    last_run_status = fields.Selection(
        RUN_STATUS_SELECTION, readonly=True, default="never"
    )
    last_period_start = fields.Date(readonly=True)
    last_period_end = fields.Date(readonly=True)
    last_row_count = fields.Integer(readonly=True)
    last_failure_on = fields.Datetime(readonly=True)
    last_error_message = fields.Text(readonly=True)
    last_failure_category = fields.Selection(FAILURE_CATEGORY_SELECTION, readonly=True)
    last_operator_message = fields.Text(readonly=True)
    consecutive_failure_count = fields.Integer(readonly=True)
    generated_file = fields.Binary(
        string="Last Generated File", attachment=True, readonly=True
    )
    generated_filename = fields.Char(readonly=True)
    notes = fields.Text()

    def _get_reporting_window(self):
        """Return the inclusive date window for the selected reporting cadence."""
        self.ensure_one()
        period_end = fields.Date.context_today(self)
        if self.period_type == "monthly":
            period_start = period_end.replace(day=1)
        else:
            period_start = period_end - timedelta(days=6)
        return period_start, period_end

    def _get_next_run_on(self, reference_dt=None):
        """Return the next scheduled execution anchored to the latest attempt."""
        self.ensure_one()
        reference_dt = fields.Datetime.to_datetime(
            reference_dt or fields.Datetime.now()
        )
        if self.period_type == "monthly":
            return fields.Datetime.to_string(reference_dt + relativedelta(months=1))
        return fields.Datetime.to_string(reference_dt + timedelta(days=7))

    def _get_effective_season(self):
        """Return the explicit season or fall back to the active season snapshot."""
        self.ensure_one()
        return report_schedule_builders.get_effective_season(self)

    def _dispatch_report_builder(self, report_type):
        """Resolve one registered scheduled report builder."""
        self.ensure_one()
        return report_schedule_builders.get_report_spec(report_type)["builder"](self)

    def _render_report_csv(self, headers, rows, period_start, period_end):
        """Serialize one scheduled report to the stored CSV contract.

        Every generated file carries the same metadata preamble so operators can
        audit cadence and window boundaries even after downloading it outside
        Odoo.
        """
        self.ensure_one()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Report",
                dict(self._fields["report_type"].selection).get(
                    self.report_type, self.report_type
                ),
            ]
        )
        writer.writerow(
            [
                "Cadence",
                dict(self._fields["period_type"].selection).get(
                    self.period_type, self.period_type
                ),
            ]
        )
        writer.writerow(["Period Start", period_start])
        writer.writerow(["Period End", period_end])
        writer.writerow([])
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)
        return output.getvalue().encode()

    def _build_operational_rows(self):
        """Build operational rows."""
        return self._dispatch_report_builder("operational")

    def _build_standing_reconciliation_rows(self):
        """Build standing reconciliation rows."""
        return self._dispatch_report_builder("standing_reconciliation")

    def _build_finance_reconciliation_rows(self):
        """Build finance reconciliation rows."""
        return self._dispatch_report_builder("finance_reconciliation")

    def _build_workflow_exception_rows(self):
        """Build workflow exception rows."""
        return self._dispatch_report_builder("workflow_exceptions")

    def _build_season_checklist_rows(self):
        """Build season checklist rows."""
        return self._dispatch_report_builder("season_checklist")

    def _build_season_portfolio_rows(self):
        """Build season portfolio rows."""
        return self._dispatch_report_builder("season_portfolio")

    def _build_club_performance_rows(self):
        """Build club performance rows."""
        return self._dispatch_report_builder("club_performance")

    def _build_compliance_summary_rows(self):
        """Build compliance summary rows."""
        return self._dispatch_report_builder("compliance_summary")

    def _build_compliance_remediation_rows(self):
        """Build compliance remediation rows."""
        return self._dispatch_report_builder("compliance_remediation")

    def _build_board_pack_rows(self):
        """Build board pack rows."""
        return self._dispatch_report_builder("board_pack")

    def _build_audit_pack_rows(self):
        """Build audit pack rows."""
        return self._dispatch_report_builder("audit_pack")

    def _build_report_payload(self):
        """Resolve the correct builder and serialize the operator-facing CSV output."""
        self.ensure_one()
        headers, rows, slug = report_schedule_builders.build_report_rows(self)

        period_start, period_end = self._get_reporting_window()
        filename = f"{slug}_{period_start}_{period_end}.csv"
        payload = self._render_report_csv(headers, rows, period_start, period_end)
        return payload, filename, len(rows), period_start, period_end

    def _generate_single_report(self, run_at=None):
        """Generate one schedule and persist either a success snapshot or failure trail.

        Failures are recorded on the schedule instead of bubbling immediately so
        cron runs can continue processing the remaining due work.
        """
        self.ensure_one()
        run_at = run_at or fields.Datetime.now()
        try:
            payload, filename, row_count, period_start, period_end = (
                self._build_report_payload()
            )
            self.write(
                {
                    "last_attempt_on": run_at,
                    "last_run_on": run_at,
                    "last_run_status": "success",
                    "last_period_start": period_start,
                    "last_period_end": period_end,
                    "last_row_count": row_count,
                    "last_failure_on": False,
                    "last_error_message": False,
                    "last_failure_category": False,
                    "last_operator_message": False,
                    "consecutive_failure_count": 0,
                    "generated_filename": filename,
                    "generated_file": base64.b64encode(payload),
                    "next_run_on": self._get_next_run_on(run_at),
                }
            )
            return False
        except Exception as error:
            failure_category, operator_message = build_failure_feedback(error=error)
            _logger.exception(
                "Scheduled report generation failed for %s (%s)",
                self.display_name,
                self.report_type,
            )
            self.write(
                {
                    "last_attempt_on": run_at,
                    "last_run_status": "failed",
                    "last_failure_on": run_at,
                    "last_error_message": False,
                    "last_failure_category": failure_category,
                    "last_operator_message": operator_message,
                    "consecutive_failure_count": self.consecutive_failure_count + 1,
                    "next_run_on": self._get_next_run_on(run_at),
                }
            )
            return operator_message

    def _generate_report(self):
        """Generate each selected report and return operator-readable failures."""
        run_at = fields.Datetime.now()
        failures = []
        for schedule in self:
            error_message = schedule._generate_single_report(run_at=run_at)
            if error_message:
                failures.append((schedule, error_message))
        return failures

    def action_generate_now(self):
        """Execute the generate now action."""
        failures = self._generate_report()
        if failures:
            raise UserError(
                "\n".join(
                    f"{schedule.display_name} [{get_failure_category_label(schedule.last_failure_category)}]: {message}"
                    for schedule, message in failures
                )
            )
        return True

    def action_open_report(self):
        """Execute the open report action."""
        self.ensure_one()
        spec = report_schedule_builders.get_report_spec(self.report_type)
        action = self.env["ir.actions.act_window"]._for_xml_id(spec["action_xmlid"])
        if spec.get("season_scoped") and self.season_id:
            action["domain"] = [("season_id", "=", self.season_id.id)]
        if spec.get("action_context"):
            action_context = action.get("context")
            if not isinstance(action_context, dict):
                action_context = {}
            else:
                action_context = dict(action_context)
            action_context.update(spec["action_context"])
            action["context"] = action_context
        return action

    @api.model
    def _cron_generate_scheduled_reports(self):
        """Process a bounded batch of due schedules so cron stays catch-up friendly."""
        schedules = self.search(
            [
                ("active", "=", True),
                ("next_run_on", "!=", False),
                ("next_run_on", "<=", fields.Datetime.now()),
            ],
            limit=20,
        )
        schedules._generate_report()

    @api.model
    def _purge_generated_files(self, reference_dt=None):
        """Clear stored report payloads after the retention window expires."""
        reference_dt = fields.Datetime.to_datetime(
            reference_dt or fields.Datetime.now()
        )
        cutoff = fields.Datetime.to_string(
            reference_dt - timedelta(days=self.GENERATED_FILE_RETENTION_DAYS)
        )
        schedules = self.search(
            [
                ("generated_file", "!=", False),
                ("last_run_on", "!=", False),
                ("last_run_on", "<", cutoff),
            ]
        )
        schedules.write(
            {
                "generated_file": False,
                "generated_filename": False,
            }
        )
        return len(schedules)

    @api.model
    def _cron_purge_generated_files(self):
        """Execute the generated-report retention policy."""
        return self._purge_generated_files()
