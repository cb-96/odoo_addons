from odoo import _, models
from odoo.exceptions import ValidationError


class FederationReportScheduleJobReliability(models.Model):
    _inherit = "federation.report.schedule"

    def action_queue_retry(self):
        for schedule in self:
            if schedule.last_run_status != "failed":
                raise ValidationError(_("Only failed report schedules can be retried."))
            correlation_id = f"report-schedule-{schedule.id}-{schedule.consecutive_failure_count}"
            job = self.env["federation.operation.job"].ensure_job(
                schedule,
                correlation_id,
                name=f"Retry report: {schedule.name}",
            )
            if job.state in ("done", "operator_action"):
                job.action_retry()
        return True

    def _retry_operational_job(self, job):
        self.ensure_one()
        self._generate_single_report()
        self.invalidate_recordset(["last_run_status", "last_operator_message"])
        if self.last_run_status == "failed":
            raise RuntimeError(self.last_operator_message or _("Scheduled report retry failed."))
        return True
