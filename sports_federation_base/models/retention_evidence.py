from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import ValidationError


class FederationRetentionPolicy(models.Model):
    _name = "federation.retention.policy"
    _description = "Retention Policy Health"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    source_model = fields.Char(required=True)
    active = fields.Boolean(default=True)
    expected_interval_hours = fields.Integer(default=24, required=True)
    policy_version = fields.Char(default="1", required=True)
    latest_evidence_id = fields.Many2one(
        "federation.retention.evidence", compute="_compute_health"
    )
    latest_success_on = fields.Datetime(compute="_compute_health")
    health = fields.Selection(
        [
            ("healthy", "Healthy"),
            ("attention", "Attention"),
            ("overdue", "Overdue"),
            ("never_run", "Never Run"),
        ],
        compute="_compute_health",
        search="_search_health",
    )
    health_message = fields.Char(compute="_compute_health")
    _unique_code = models.Constraint(
        "unique(code)", "Retention policy codes must be unique."
    )

    @api.constrains("expected_interval_hours")
    def _check_expected_interval(self):
        if any(policy.expected_interval_hours < 1 for policy in self):
            raise ValidationError(_("Expected retention intervals must be positive."))

    def _compute_health(self):
        now = fields.Datetime.now()
        Evidence = self.env["federation.retention.evidence"].sudo()
        for policy in self:
            latest = Evidence.search(
                [("policy", "=", policy.code)],
                order="completed_on desc,id desc",
                limit=1,
            )
            latest_success = Evidence.search(
                [("policy", "=", policy.code), ("status", "=", "passed")],
                order="completed_on desc,id desc",
                limit=1,
            )
            policy.latest_evidence_id = latest
            policy.latest_success_on = latest_success.completed_on
            if not latest:
                policy.health = "never_run"
                policy.health_message = _("No execution evidence has been recorded.")
            elif latest.status == "failed":
                policy.health = "attention"
                policy.health_message = latest.operator_message or _(
                    "The latest retention execution failed."
                )
            elif (
                now - latest.completed_on
            ).total_seconds() / 3600 > policy.expected_interval_hours:
                policy.health = "overdue"
                policy.health_message = _(
                    "No successful execution within the expected interval."
                )
            elif latest.skipped_count or latest.failure_count:
                policy.health = "attention"
                policy.health_message = _(
                    "The latest execution completed with skipped records or failures."
                )
            else:
                policy.health = "healthy"
                policy.health_message = _(
                    "The latest execution completed successfully."
                )

    @api.model
    def _search_health(self, operator, value):
        policies = self.search([])
        if operator in ("=", "=="):
            matched = policies.filtered(lambda policy: policy.health == value)
        elif operator == "in":
            matched = policies.filtered(lambda policy: policy.health in value)
        elif operator in ("!=", "<>"):
            matched = policies.filtered(lambda policy: policy.health != value)
        elif operator == "not in":
            matched = policies.filtered(lambda policy: policy.health not in value)
        else:
            raise ValidationError(_("Unsupported retention health search operator."))
        return [("id", "in", matched.ids)]

    def action_open_evidence(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "sports_federation_base.action_federation_retention_evidence"
        )
        action["domain"] = [("policy", "=", self.code)]
        return action


class FederationRetentionEvidence(models.Model):
    _name = "federation.retention.evidence"
    _description = "Retention Execution Evidence"
    _order = "started_on desc, id desc"

    policy = fields.Char(required=True, index=True)
    policy_version = fields.Char(default="1", required=True)
    source_model = fields.Char(index=True)
    started_on = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    completed_on = fields.Datetime(required=True, default=fields.Datetime.now)
    duration_seconds = fields.Float(readonly=True)
    candidate_count = fields.Integer(required=True, default=0)
    deleted_count = fields.Integer(required=True, default=0)
    skipped_count = fields.Integer(required=True, default=0)
    attachment_count = fields.Integer(required=True, default=0)
    failure_count = fields.Integer(required=True, default=0)
    status = fields.Selection(
        [("passed", "Passed"), ("failed", "Failed")], required=True, index=True
    )
    dry_run = fields.Boolean(default=False, index=True)
    retention_rules = fields.Json()
    operator_message = fields.Text()
    correlation_id = fields.Char(index=True)

    @api.model
    def record_failure_durable(self, policy, **values):
        """Commit failure evidence independently before the owning cron re-raises."""
        values["status"] = "failed"
        with self.env.registry.cursor() as cursor:
            env = api.Environment(cursor, SUPERUSER_ID, dict(self.env.context))
            evidence = env["federation.retention.evidence"].record_execution(
                policy, **values
            )
            evidence_id = evidence.id
            cursor.commit()
        return self.browse(evidence_id)

    @api.model
    def record_execution(
        self,
        policy,
        *,
        started_on,
        candidate_count=0,
        deleted_count=0,
        skipped_count=0,
        attachment_count=0,
        failure_count=0,
        status="passed",
        dry_run=False,
        retention_rules=None,
        operator_message=False,
        correlation_id=False,
        source_model=False
    ):
        completed_on = fields.Datetime.now()
        policy_record = (
            self.env["federation.retention.policy"]
            .sudo()
            .search([("code", "=", policy)], limit=1)
        )
        duration = max(
            0,
            (
                fields.Datetime.to_datetime(completed_on)
                - fields.Datetime.to_datetime(started_on)
            ).total_seconds(),
        )
        return self.sudo().create(
            {
                "policy": policy,
                "policy_version": policy_record.policy_version or "1",
                "source_model": source_model or policy_record.source_model,
                "started_on": started_on,
                "completed_on": completed_on,
                "duration_seconds": duration,
                "candidate_count": candidate_count,
                "deleted_count": deleted_count,
                "skipped_count": skipped_count,
                "attachment_count": attachment_count,
                "failure_count": failure_count,
                "status": status,
                "dry_run": dry_run,
                "retention_rules": retention_rules or {},
                "operator_message": operator_message,
                "correlation_id": correlation_id,
            }
        )
