from odoo import api, fields, models


class FederationReportSnapshot(models.Model):
    _name = "federation.report.snapshot"
    _description = "Federation Report Snapshot"
    _order = "snapshot_on desc, snapshot_type asc, id desc"

    SNAPSHOT_TYPE_SELECTION = [
        ("override_backlog", "Override Backlog"),
        ("sanction_exposure", "Sanction Exposure"),
        ("compliance_posture", "Compliance Posture"),
        ("finance_follow_up", "Finance Follow-up"),
        ("seasonal_readiness", "Seasonal Readiness"),
    ]
    STATUS_SELECTION = [
        ("healthy", "Healthy"),
        ("attention", "Attention"),
        ("blocked", "Blocked"),
    ]

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    snapshot_on = fields.Date(
        string="Snapshot Date", required=True, default=fields.Date.context_today
    )
    snapshot_type = fields.Selection(
        SNAPSHOT_TYPE_SELECTION, string="Snapshot Type", required=True
    )
    current_value = fields.Integer(string="Current Value", required=True)
    previous_value = fields.Integer(string="Previous Value", default=0)
    delta_value = fields.Integer(
        string="Delta", compute="_compute_delta_value", store=True
    )
    status = fields.Selection(STATUS_SELECTION, string="Status")
    note = fields.Char(string="Summary")

    _snapshot_unique = models.Constraint(
        "UNIQUE(snapshot_on, snapshot_type)",
        "A snapshot already exists for this date and snapshot type.",
    )

    @api.depends("snapshot_on", "snapshot_type")
    def _compute_name(self):
        """Compute name."""
        labels = dict(self._fields["snapshot_type"].selection)
        for record in self:
            label = labels.get(record.snapshot_type, record.snapshot_type or "Snapshot")
            record.name = (
                f"{label} - {record.snapshot_on}" if record.snapshot_on else label
            )

    @api.depends("current_value", "previous_value")
    def _compute_delta_value(self):
        """Compute delta value."""
        for record in self:
            record.delta_value = (record.current_value or 0) - (
                record.previous_value or 0
            )

    @api.model
    def _build_snapshot_rows(self):
        """Build snapshot rows."""
        workflow_model = self.env["federation.report.workflow.exception"]
        compliance_model = self.env["federation.report.compliance"]
        finance_follow_up_model = self.env["federation.report.finance.reconciliation"]
        finance_exception_model = self.env["federation.report.finance.exception"]
        season_checklist_model = self.env["federation.report.season.checklist"]

        override_backlog = workflow_model.search_count(
            [
                (
                    "exception_type",
                    "in",
                    ("override_review_stalled", "override_implementation_stalled"),
                ),
            ]
        )
        sanction_exposure = finance_exception_model.search_count([])
        compliance_rows = compliance_model.search([])
        compliance_pending = sum(
            row.pending_count + row.expired_count + row.non_compliant_count
            for row in compliance_rows
        )
        finance_follow_up = finance_follow_up_model.search_count(
            [
                ("needs_follow_up", "=", True),
            ]
        )
        season_rows = season_checklist_model.search([])
        blocked_seasons = len(
            season_rows.filtered(lambda row: row.checklist_status == "blocked")
        )
        attention_seasons = len(
            season_rows.filtered(lambda row: row.checklist_status == "attention")
        )
        seasonal_readiness = blocked_seasons + attention_seasons

        return [
            {
                "snapshot_type": "override_backlog",
                "current_value": override_backlog,
                "status": "blocked" if override_backlog else "healthy",
                "note": (
                    "Governance overrides are still waiting for review or implementation."
                    if override_backlog
                    else "No override backlog is currently open."
                ),
            },
            {
                "snapshot_type": "sanction_exposure",
                "current_value": sanction_exposure,
                "status": "attention" if sanction_exposure else "healthy",
                "note": (
                    "Disciplinary fine events still need finance follow-up."
                    if sanction_exposure
                    else "No sanction-side finance gaps are currently open."
                ),
            },
            {
                "snapshot_type": "compliance_posture",
                "current_value": compliance_pending,
                "status": "blocked" if compliance_pending else "healthy",
                "note": (
                    "Compliance submissions still require review, renewal, or remediation."
                    if compliance_pending
                    else "Compliance posture is currently clear."
                ),
            },
            {
                "snapshot_type": "finance_follow_up",
                "current_value": finance_follow_up,
                "status": "attention" if finance_follow_up else "healthy",
                "note": (
                    "Finance events are still waiting for settlement or references."
                    if finance_follow_up
                    else "No finance follow-up queue is currently open."
                ),
            },
            {
                "snapshot_type": "seasonal_readiness",
                "current_value": seasonal_readiness,
                "status": (
                    "blocked"
                    if blocked_seasons
                    else "attention" if attention_seasons else "healthy"
                ),
                "note": (
                    f"{blocked_seasons} blocked season(s), {attention_seasons} attention season(s)."
                    if seasonal_readiness
                    else "All season readiness checklists are currently healthy."
                ),
            },
        ]

    @api.model
    def capture_snapshot(self, snapshot_on=None):
        """Handle capture snapshot."""
        snapshot_on = (
            fields.Date.to_date(snapshot_on)
            if snapshot_on
            else fields.Date.context_today(self)
        )
        records = self.browse([])
        for row in self._build_snapshot_rows():
            previous = self.search(
                [
                    ("snapshot_type", "=", row["snapshot_type"]),
                    ("snapshot_on", "<", snapshot_on),
                ],
                order="snapshot_on desc, id desc",
                limit=1,
            )
            values = {
                **row,
                "snapshot_on": snapshot_on,
                "previous_value": previous.current_value if previous else 0,
            }
            existing = self.search(
                [
                    ("snapshot_type", "=", row["snapshot_type"]),
                    ("snapshot_on", "=", snapshot_on),
                ],
                limit=1,
            )
            if existing:
                existing.write(values)
                records |= existing
            else:
                records |= self.create(values)
        return records

    @api.model
    def _cron_capture_snapshots(self):
        """Handle cron capture snapshots."""
        self.capture_snapshot()
