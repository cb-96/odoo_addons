import logging
from datetime import timedelta

from odoo.addons.sports_federation_base.correlation import ensure_correlation_id
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class FederationStandingRecomputeJob(models.Model):
    _name = "federation.standing.recompute.job"
    _description = "Federation Standing Recompute Job"
    _order = "priority desc, requested_on asc, id asc"

    STATE_SELECTION = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Retry scheduled"),
        ("dead_letter", "Needs operator action"),
    ]

    name = fields.Char(compute="_compute_name", store=True)
    standing_id = fields.Many2one(
        "federation.standing",
        required=True,
        ondelete="cascade",
        index=True,
    )
    idempotency_key = fields.Char(index=True)
    correlation_id = fields.Char(required=True, index=True)
    state = fields.Selection(
        STATE_SELECTION, default="pending", required=True, index=True
    )
    priority = fields.Integer(default=50, index=True)
    requested_on = fields.Datetime(
        default=fields.Datetime.now, required=True, index=True
    )
    started_on = fields.Datetime()
    completed_on = fields.Datetime(index=True)
    next_retry_on = fields.Datetime(index=True)
    attempt_count = fields.Integer(default=0)
    max_attempts = fields.Integer(default=3)
    last_error = fields.Text()
    dead_lettered_on = fields.Datetime(index=True)
    replayed_from_job_id = fields.Many2one(
        "federation.standing.recompute.job",
        string="Replayed From",
        ondelete="set null",
    )
    requested_by_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        required=True,
        ondelete="restrict",
    )

    _unique_idempotency_key = models.Constraint(
        "UNIQUE(standing_id, idempotency_key)",
        "This standing already has a recompute job with the same idempotency key.",
    )

    @api.depends("standing_id", "state", "requested_on")
    def _compute_name(self):
        for record in self:
            requested_on = (
                fields.Datetime.to_string(record.requested_on)
                if record.requested_on
                else ""
            )
            record.name = "%s [%s] %s" % (
                record.standing_id.display_name or _("Standing"),
                record.state,
                requested_on,
            )

    @api.model
    def _normalize_idempotency_key(self, idempotency_key=False):
        if idempotency_key in (False, None):
            return False
        key = str(idempotency_key).strip()
        if not key:
            return False
        if len(key) > 120:
            raise ValidationError(_("Idempotency keys must not exceed 120 characters."))
        return key

    @api.model
    def _normalize_correlation_id(self, correlation_id=False):
        return ensure_correlation_id(self.env, correlation_id)

    @api.model
    def request_recompute(
        self,
        standing,
        idempotency_key=False,
        correlation_id=False,
        priority=50,
    ):
        standing.ensure_one()
        key = self._normalize_idempotency_key(idempotency_key)
        normalized_correlation_id = self._normalize_correlation_id(correlation_id)

        replayed_from = False
        if key:
            replayed_from = self.search(
                [
                    ("standing_id", "=", standing.id),
                    ("idempotency_key", "=", key),
                ],
                limit=1,
            )
            if replayed_from:
                return {
                    "job": replayed_from,
                    "replayed": True,
                    "correlation_id": replayed_from.correlation_id,
                    "idempotency_key": key,
                }

        job = self.create(
            {
                "standing_id": standing.id,
                "idempotency_key": key,
                "correlation_id": normalized_correlation_id,
                "priority": priority,
                "replayed_from_job_id": replayed_from.id if replayed_from else False,
            }
        )
        return {
            "job": job,
            "replayed": False,
            "correlation_id": normalized_correlation_id,
            "idempotency_key": key,
        }

    def _process_single_job(self):
        self.ensure_one()
        if self.state not in ("pending", "failed"):
            return False
        if self.next_retry_on and self.next_retry_on > fields.Datetime.now():
            return False

        self.write(
            {
                "state": "running",
                "started_on": fields.Datetime.now(),
                "attempt_count": self.attempt_count + 1,
                "last_error": False,
            }
        )
        try:
            self.standing_id.with_context(
                force_recompute=True,
                federation_correlation_id=self.correlation_id,
            ).action_recompute()
        except Exception as error:  # pylint: disable=broad-except
            exhausted = self.attempt_count >= self.max_attempts
            retry_minutes = min(60, 2 ** max(1, self.attempt_count))
            next_retry_on = (
                False
                if exhausted
                else fields.Datetime.now() + timedelta(minutes=retry_minutes)
            )
            self.write(
                {
                    "state": "dead_letter" if exhausted else "failed",
                    "completed_on": fields.Datetime.now(),
                    "next_retry_on": (
                        fields.Datetime.to_string(next_retry_on)
                        if next_retry_on
                        else False
                    ),
                    "last_error": str(error)[:4000],
                    "dead_lettered_on": fields.Datetime.now() if exhausted else False,
                }
            )
            _logger.exception(
                "Standing recompute job failed: job=%s standing=%s correlation_id=%s",
                self.id,
                self.standing_id.id,
                self.correlation_id,
            )
            return False

        self.write(
            {
                "state": "done",
                "completed_on": fields.Datetime.now(),
                "next_retry_on": False,
                "last_error": False,
            }
        )
        _logger.info(
            "Standing recompute job completed: job=%s standing=%s correlation_id=%s",
            self.id,
            self.standing_id.id,
            self.correlation_id,
        )
        return True

    def action_retry(self):
        """Return terminal jobs to the queue without erasing evidence."""
        for job in self:
            if job.state not in ("failed", "dead_letter"):
                raise ValidationError(_("Only failed jobs can be retried."))
            job.write(
                {
                    "state": "pending",
                    "next_retry_on": False,
                    "completed_on": False,
                    "dead_lettered_on": False,
                    "attempt_count": 0,
                }
            )
        return True

    @api.model
    def _recover_stale_running_jobs(self, stale_minutes=30):
        deadline = fields.Datetime.now() - timedelta(minutes=stale_minutes)
        stale = self.search([("state", "=", "running"), ("started_on", "<=", deadline)])
        stale.write(
            {
                "state": "failed",
                "next_retry_on": fields.Datetime.now(),
                "last_error": _("Recovered after the worker stopped while processing."),
            }
        )
        return len(stale)

    @api.model
    def _cron_process_queue(self):
        self._recover_stale_running_jobs()
        jobs = self.search(
            [
                ("state", "in", ("pending", "failed")),
                "|",
                ("next_retry_on", "=", False),
                ("next_retry_on", "<=", fields.Datetime.now()),
            ],
            order="priority desc, requested_on asc, id asc",
            limit=20,
        )
        processed = 0
        for job in jobs:
            if job._process_single_job():
                processed += 1
        return processed
