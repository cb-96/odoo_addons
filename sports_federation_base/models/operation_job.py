import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class FederationOperationJob(models.Model):
    _name = "federation.operation.job"
    _description = "Operational Job"
    _order = "priority desc, requested_on asc, id asc"

    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("running", "Running"),
            ("retry", "Retry Scheduled"),
            ("done", "Done"),
            ("operator_action", "Needs Operator Action"),
        ],
        default="pending",
        required=True,
        index=True,
    )
    name = fields.Char(required=True)
    source_model = fields.Char(required=True, index=True)
    source_res_id = fields.Integer(required=True, index=True)
    correlation_id = fields.Char(required=True, index=True)
    priority = fields.Integer(default=50, index=True)
    requested_on = fields.Datetime(
        default=fields.Datetime.now, required=True, index=True
    )
    started_on = fields.Datetime(index=True)
    completed_on = fields.Datetime(index=True)
    next_retry_on = fields.Datetime(index=True)
    operator_action_on = fields.Datetime(index=True)
    attempt_count = fields.Integer(default=0, required=True)
    max_attempts = fields.Integer(default=3, required=True)
    last_error = fields.Text(readonly=True)
    failure_category = fields.Char(index=True, readonly=True)

    _unique_source_correlation = models.Constraint(
        "unique(source_model, source_res_id, correlation_id)",
        "A source record can have only one job for a correlation ID.",
    )

    @api.constrains("attempt_count", "max_attempts")
    def _check_attempts(self):
        for job in self:
            if job.attempt_count < 0 or job.max_attempts < 1:
                raise ValidationError(_("Job attempt limits are invalid."))

    @api.model
    def ensure_job(
        self, source, correlation_id, name=False, max_attempts=3, priority=50
    ):
        source.ensure_one()
        values = {
            "name": name or source.display_name,
            "source_model": source._name,
            "source_res_id": source.id,
            "correlation_id": correlation_id,
            "max_attempts": max_attempts,
            "priority": priority,
        }
        job = self.search(
            [
                ("source_model", "=", source._name),
                ("source_res_id", "=", source.id),
                ("correlation_id", "=", correlation_id),
            ],
            limit=1,
        )
        return job or self.create(values)

    def _source(self):
        self.ensure_one()
        model = self.env.get(self.source_model)
        return model.browse(self.source_res_id).exists() if model is not None else model

    def _start(self):
        self.ensure_one()
        self.write(
            {
                "state": "running",
                "started_on": fields.Datetime.now(),
                "completed_on": False,
                "next_retry_on": False,
                "attempt_count": self.attempt_count + 1,
            }
        )

    def _succeed(self):
        self.write(
            {
                "state": "done",
                "completed_on": fields.Datetime.now(),
                "next_retry_on": False,
                "operator_action_on": False,
                "last_error": False,
                "failure_category": False,
            }
        )

    def _fail(self, error, category="unexpected_bug", retryable=True):
        self.ensure_one()
        exhausted = self.attempt_count >= self.max_attempts or not retryable
        delay_minutes = min(60, 2 ** max(1, self.attempt_count))
        self.write(
            {
                "state": "operator_action" if exhausted else "retry",
                "completed_on": fields.Datetime.now(),
                "next_retry_on": (
                    False
                    if exhausted
                    else fields.Datetime.now() + timedelta(minutes=delay_minutes)
                ),
                "operator_action_on": fields.Datetime.now() if exhausted else False,
                "last_error": str(error)[:4000],
                "failure_category": category,
            }
        )

    def _execute(self):
        self.ensure_one()
        source = self._source()
        if not source:
            self._fail(
                _("The source record no longer exists."),
                "data_validation",
                retryable=False,
            )
            return False
        self._start()
        try:
            source.with_context(
                federation_correlation_id=self.correlation_id
            )._retry_operational_job(self)
        except Exception as error:  # pylint: disable=broad-except
            retryable = not isinstance(error, (UserError, ValidationError))
            self._fail(error, "unexpected_bug", retryable=retryable)
            _logger.exception(
                "Operational job failed: job=%s correlation_id=%s",
                self.id,
                self.correlation_id,
            )
            return False
        self._succeed()
        return True

    def action_retry(self):
        for job in self:
            if job.state not in ("retry", "operator_action"):
                raise ValidationError(_("Only failed jobs can be retried."))
            job.write(
                {
                    "state": "pending",
                    "attempt_count": 0,
                    "next_retry_on": False,
                    "operator_action_on": False,
                }
            )
        return True

    def action_open_source(self):
        self.ensure_one()
        source = self._source()
        if not source:
            raise UserError(_("The source record no longer exists."))
        return {
            "type": "ir.actions.act_window",
            "res_model": source._name,
            "res_id": source.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def _recover_stale(self, stale_minutes=30):
        deadline = fields.Datetime.now() - timedelta(minutes=stale_minutes)
        stale = self.search([("state", "=", "running"), ("started_on", "<=", deadline)])
        for job in stale:
            job._fail(
                _("Recovered after the worker stopped while processing."),
                "infrastructure",
            )
        return len(stale)

    @api.model
    def _cron_process_jobs(self):
        self._recover_stale()
        jobs = self.search(
            [
                ("state", "in", ("pending", "retry")),
                "|",
                ("next_retry_on", "=", False),
                ("next_retry_on", "<=", fields.Datetime.now()),
            ],
            order="priority desc, requested_on asc, id asc",
            limit=50,
        )
        return sum(1 for job in jobs if job._execute())
