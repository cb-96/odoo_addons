from datetime import timedelta

from odoo import _, api, fields, models


class FederationOperationalDashboard(models.TransientModel):
    _name = "federation.operational.dashboard"
    _description = "Consolidated Operational Dashboard"

    name = fields.Char(default="Operational Health", readonly=True)
    refreshed_on = fields.Datetime(default=fields.Datetime.now, readonly=True)
    release_status = fields.Selection(
        [
            ("unknown", "Evidence Not Recorded"),
            ("passed", "Ready"),
            ("failed", "Blocked"),
        ],
        default="unknown",
        readonly=True,
    )
    release_candidate_sha = fields.Char(readonly=True)
    release_completed_on = fields.Datetime(readonly=True)
    release_evidence_url = fields.Char(readonly=True)
    queued_job_count = fields.Integer(readonly=True)
    retrying_job_count = fields.Integer(readonly=True)
    operator_action_job_count = fields.Integer(readonly=True)
    stale_job_count = fields.Integer(readonly=True)
    retention_attention_count = fields.Integer(readonly=True)
    retention_failed_count = fields.Integer(readonly=True)
    integration_failure_count = fields.Integer(readonly=True)
    registration_blocker_count = fields.Integer(readonly=True)
    review_backlog_count = fields.Integer(readonly=True)
    unpublished_approved_count = fields.Integer(readonly=True)
    publication_gap_count = fields.Integer(readonly=True)
    result_backlog_count = fields.Integer(readonly=True)
    standings_failure_count = fields.Integer(readonly=True)
    overall_status = fields.Selection(
        [
            ("healthy", "Healthy"),
            ("attention", "Attention Required"),
            ("blocked", "Blocked"),
        ],
        default="healthy",
        readonly=True,
    )
    overall_message = fields.Text(readonly=True)

    @api.model
    def _safe_count(self, model_name, domain):
        if model_name not in self.env:
            return 0
        return self.env[model_name].sudo().search_count(domain)

    @api.model
    def _snapshot_values(self):
        now = fields.Datetime.now()
        params = self.env["ir.config_parameter"].sudo()
        release_status = params.get_param(
            "sports_federation.release.last_status", "unknown"
        )
        if release_status not in {"passed", "failed"}:
            release_status = "unknown"
        values = {
            "refreshed_on": now,
            "release_status": release_status,
            "release_candidate_sha": params.get_param(
                "sports_federation.release.last_sha"
            )
            or False,
            "release_completed_on": params.get_param(
                "sports_federation.release.last_completed_on"
            )
            or False,
            "release_evidence_url": params.get_param(
                "sports_federation.release.evidence_url"
            )
            or False,
            "queued_job_count": self._safe_count(
                "federation.operation.job", [("state", "=", "pending")]
            ),
            "retrying_job_count": self._safe_count(
                "federation.operation.job", [("state", "=", "retry")]
            ),
            "operator_action_job_count": self._safe_count(
                "federation.operation.job", [("state", "=", "operator_action")]
            ),
            "stale_job_count": self._safe_count(
                "federation.operation.job",
                [
                    ("state", "=", "running"),
                    ("started_on", "<", now - timedelta(minutes=15)),
                ],
            ),
            "retention_attention_count": self._safe_count(
                "federation.retention.policy",
                [("health", "in", ["attention", "overdue", "never_run"])],
            ),
            "retention_failed_count": self._safe_count(
                "federation.retention.evidence", [("status", "=", "failed")]
            ),
            "integration_failure_count": self._safe_count(
                "federation.integration.delivery",
                [("state", "in", ["processed_with_errors", "failed"])],
            ),
            "registration_blocker_count": self._safe_count(
                "federation.competition.entry",
                [("state", "in", ["submitted", "rejected"])],
            ),
            "review_backlog_count": self._safe_count(
                "federation.schedule.review", [("state", "=", "pending")]
            ),
            "unpublished_approved_count": self._safe_count(
                "federation.schedule", [("state", "=", "approved")]
            ),
            "publication_gap_count": self._safe_count(
                "federation.matchday",
                [
                    ("state", "in", ["scheduled", "open"]),
                    ("current_publication_id", "=", False),
                ],
            ),
            "result_backlog_count": self._safe_count(
                "federation.match",
                [
                    (
                        "result_state",
                        "in",
                        ["submitted", "verified", "contested", "corrected"],
                    )
                ],
            ),
            "standings_failure_count": self._safe_count(
                "federation.operation.job",
                [
                    ("state", "=", "operator_action"),
                    (
                        "source_model",
                        "in",
                        ["federation.standing", "federation.tournament"],
                    ),
                ],
            ),
        }
        blocked = sum(
            values[key]
            for key in (
                "operator_action_job_count",
                "stale_job_count",
                "retention_failed_count",
                "integration_failure_count",
                "publication_gap_count",
                "standings_failure_count",
            )
        )
        attention = sum(
            values[key]
            for key in (
                "retrying_job_count",
                "retention_attention_count",
                "registration_blocker_count",
                "review_backlog_count",
                "unpublished_approved_count",
                "result_backlog_count",
            )
        )
        if release_status == "failed" or blocked:
            values.update(
                overall_status="blocked",
                overall_message=_(
                    "One or more operational queues require immediate remediation."
                ),
            )
        elif release_status == "unknown" or attention:
            values.update(
                overall_status="attention",
                overall_message=_(
                    "Operational work is pending or release evidence has not been recorded."
                ),
            )
        else:
            values.update(
                overall_status="healthy",
                overall_message=_("No blocking operational conditions were found."),
            )
        return values

    @api.model
    def action_open_dashboard(self):
        dashboard = self.create(self._snapshot_values())
        return {
            "type": "ir.actions.act_window",
            "name": _("Operational Health"),
            "res_model": self._name,
            "res_id": dashboard.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_refresh(self):
        self.ensure_one()
        self.write(self._snapshot_values())
        return {"type": "ir.actions.client", "tag": "reload"}

    def _open_queue(self, model_name, domain, name):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model_name,
            "view_mode": "list,form",
            "domain": domain,
            "target": "current",
        }

    def action_open_jobs(self):
        return self._open_queue(
            "federation.operation.job",
            [("state", "in", ["pending", "retry", "operator_action", "running"])],
            _("Operational Jobs"),
        )

    def action_open_retention(self):
        return self._open_queue(
            "federation.retention.policy", [], _("Retention and Recovery")
        )

    def action_open_integrations(self):
        return self._open_queue(
            "federation.integration.delivery",
            [("state", "in", ["processed_with_errors", "failed"])],
            _("Integration Deliveries"),
        )

    def action_open_registrations(self):
        return self._open_queue(
            "federation.competition.entry",
            [("state", "in", ["submitted", "rejected"])],
            _("Registration Blockers"),
        )

    def action_open_reviews(self):
        return self._open_queue(
            "federation.schedule.review",
            [("state", "=", "pending")],
            _("Schedule Review Backlog"),
        )

    def action_open_unpublished(self):
        return self._open_queue(
            "federation.schedule",
            [("state", "=", "approved")],
            _("Approved Schedules Awaiting Publication"),
        )

    def action_open_publication_gaps(self):
        return self._open_queue(
            "federation.matchday",
            [
                ("state", "in", ["scheduled", "open"]),
                ("current_publication_id", "=", False),
            ],
            _("Match-Day Publication Gaps"),
        )

    def action_open_results(self):
        return self._open_queue(
            "federation.match",
            [
                (
                    "result_state",
                    "in",
                    ["submitted", "verified", "contested", "corrected"],
                )
            ],
            _("Result Backlog"),
        )

    def action_open_standings_failures(self):
        return self._open_queue(
            "federation.operation.job",
            [
                ("state", "=", "operator_action"),
                (
                    "source_model",
                    "in",
                    ["federation.standing", "federation.tournament"],
                ),
            ],
            _("Standings Failures"),
        )

    def action_open_release_evidence(self):
        self.ensure_one()
        if not self.release_evidence_url:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Release evidence"),
                    "message": _("No release evidence URL has been recorded."),
                    "type": "warning",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.act_url",
            "url": self.release_evidence_url,
            "target": "new",
        }
