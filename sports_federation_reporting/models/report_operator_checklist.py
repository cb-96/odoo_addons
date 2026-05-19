from odoo import fields, models, tools


class FederationReportOperatorChecklist(models.Model):
    _name = "federation.report.operator.checklist"
    _description = "Federation Operator Checklist"
    _auto = False
    _order = "status_priority desc, open_count desc, queue_name"

    STATUS_SELECTION = [
        ("healthy", "Healthy"),
        ("attention", "Attention"),
        ("blocked", "Blocked"),
    ]
    QUEUE_SELECTION = [
        ("workflow_exceptions", "Workflow Exceptions"),
        ("compliance_remediation", "Compliance Remediation"),
        ("finance_follow_up", "Finance Follow-up"),
        ("notification_exceptions", "Notification Exceptions"),
        ("sanction_finance_gaps", "Sanction Finance Gaps"),
        ("season_readiness", "Season Readiness"),
        ("inbound_delivery_failures", "Inbound Delivery Failures"),
        ("scheduled_report_failures", "Scheduled Report Failures"),
    ]

    queue_code = fields.Selection(QUEUE_SELECTION, string="Queue", readonly=True)
    queue_name = fields.Char(string="Queue Name", readonly=True)
    owner_display = fields.Char(string="Owner", readonly=True)
    open_count = fields.Integer(string="Open Items", readonly=True)
    escalated_count = fields.Integer(string="Escalated Items", readonly=True)
    oldest_age_days = fields.Integer(string="Oldest Age (Days)", readonly=True)
    status = fields.Selection(STATUS_SELECTION, string="Status", readonly=True)
    status_priority = fields.Integer(string="Status Priority", readonly=True)
    summary = fields.Text(string="Summary", readonly=True)
    action_xmlid = fields.Char(string="Action XMLID", readonly=True)

    def action_open_queue(self):
        """Open the underlying queue action for this checklist row."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(self.action_xmlid)
        if self.queue_code == "finance_follow_up":
            action["domain"] = [("needs_follow_up", "=", True)]
        elif self.queue_code == "season_readiness":
            action["domain"] = [("checklist_status", "=", "blocked")]
        elif self.queue_code == "inbound_delivery_failures":
            action["domain"] = [("state", "in", ("failed", "processed_with_errors"))]
        elif self.queue_code == "scheduled_report_failures":
            action["domain"] = [("last_run_status", "=", "failed")]
        return action

    def init(self):
        """Create the SQL view for the operator checklist."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_operator_checklist AS (
                WITH queue_rows AS (
                    SELECT
                        'workflow_exceptions'::varchar AS queue_code,
                        'Workflow Exceptions'::varchar AS queue_name,
                        COALESCE(MAX(queue_owner_display), 'Federation Managers')::varchar AS owner_display,
                        COUNT(*)::int AS open_count,
                        COUNT(*) FILTER (WHERE sla_status = 'escalated')::int AS escalated_count,
                        COALESCE(MAX(age_days), 0)::int AS oldest_age_days,
                        CASE
                            WHEN COUNT(*) FILTER (WHERE sla_status = 'escalated') > 0 THEN 'blocked'
                            WHEN COUNT(*) > 0 THEN 'attention'
                            ELSE 'healthy'
                        END::varchar AS status,
                        'Result approval and governance override backlog requiring operator action.'::text AS summary,
                        'sports_federation_reporting.action_federation_report_workflow_exception'::varchar AS action_xmlid
                    FROM federation_report_workflow_exception

                    UNION ALL

                    SELECT
                        'compliance_remediation'::varchar,
                        'Compliance Remediation'::varchar,
                        COALESCE(MAX(queue_owner_display), 'Compliance Review Queue')::varchar,
                        COUNT(*)::int,
                        COUNT(*) FILTER (WHERE sla_status = 'escalated')::int,
                        COALESCE(MAX(age_days), 0)::int,
                        CASE
                            WHEN COUNT(*) FILTER (WHERE sla_status = 'escalated') > 0 THEN 'blocked'
                            WHEN COUNT(*) > 0 THEN 'attention'
                            ELSE 'healthy'
                        END::varchar,
                        'Submitted, rejected, or expired documents waiting for review or renewal.'::text,
                        'sports_federation_reporting.action_federation_report_compliance_remediation'::varchar
                    FROM federation_report_compliance_remediation

                    UNION ALL

                    SELECT
                        'finance_follow_up'::varchar,
                        'Finance Follow-up'::varchar,
                        COALESCE(MAX(queue_owner_display), 'Federation Managers')::varchar,
                        COUNT(*)::int,
                        COUNT(*) FILTER (WHERE sla_status = 'escalated')::int,
                        COALESCE(MAX(age_days), 0)::int,
                        CASE
                            WHEN COUNT(*) FILTER (WHERE sla_status = 'escalated') > 0 THEN 'blocked'
                            WHEN COUNT(*) > 0 THEN 'attention'
                            ELSE 'healthy'
                        END::varchar,
                        'Finance events still waiting for settlement or reconciliation references.'::text,
                        'sports_federation_reporting.action_federation_report_finance_reconciliation'::varchar
                    FROM federation_report_finance_reconciliation
                    WHERE needs_follow_up = TRUE

                    UNION ALL

                    SELECT
                        'notification_exceptions'::varchar,
                        'Notification Exceptions'::varchar,
                        COALESCE(MAX(queue_owner_display), 'Federation Managers')::varchar,
                        COUNT(*)::int,
                        COUNT(*) FILTER (WHERE sla_status = 'escalated')::int,
                        COALESCE(MAX(age_days), 0)::int,
                        CASE
                            WHEN COUNT(*) FILTER (WHERE sla_status = 'escalated') > 0 THEN 'blocked'
                            WHEN COUNT(*) > 0 THEN 'attention'
                            ELSE 'healthy'
                        END::varchar,
                        'Failed outbound notifications that still need a delivery or data fix.'::text,
                        'sports_federation_reporting.action_federation_report_notification_exception'::varchar
                    FROM federation_report_notification_exception

                    UNION ALL

                    SELECT
                        'sanction_finance_gaps'::varchar,
                        'Sanction Finance Gaps'::varchar,
                        'Federation Managers'::varchar,
                        COUNT(*)::int,
                        COUNT(*)::int,
                        0::int,
                        CASE
                            WHEN COUNT(*) > 0 THEN 'blocked'
                            ELSE 'healthy'
                        END::varchar,
                        'Disciplinary fines missing their linked finance events.'::text,
                        'sports_federation_reporting.action_federation_report_finance_exception'::varchar
                    FROM federation_report_finance_exception

                    UNION ALL

                    SELECT
                        'season_readiness'::varchar,
                        'Season Readiness'::varchar,
                        'Federation Managers'::varchar,
                        COUNT(*)::int,
                        COUNT(*)::int,
                        0::int,
                        CASE
                            WHEN COUNT(*) > 0 THEN 'blocked'
                            ELSE 'healthy'
                        END::varchar,
                        'Blocked season checklists that need operational intervention before release sign-off.'::text,
                        'sports_federation_reporting.action_federation_report_season_checklist'::varchar
                    FROM federation_report_season_checklist
                    WHERE checklist_status = 'blocked'

                    UNION ALL

                    SELECT
                        'inbound_delivery_failures'::varchar,
                        'Inbound Delivery Failures'::varchar,
                        'Integration Operators'::varchar,
                        COUNT(*)::int,
                        COUNT(*) FILTER (WHERE state = 'failed')::int,
                        COALESCE(MAX((CURRENT_DATE - COALESCE(received_on::date, CURRENT_DATE))::int), 0)::int,
                        CASE
                            WHEN COUNT(*) FILTER (WHERE state = 'failed') > 0 THEN 'blocked'
                            WHEN COUNT(*) > 0 THEN 'attention'
                            ELSE 'healthy'
                        END::varchar,
                        'Partner deliveries that failed preview/import or completed with row-level errors.'::text,
                        'sports_federation_import_tools.action_federation_integration_deliveries'::varchar
                    FROM federation_integration_delivery
                    WHERE state IN ('failed', 'processed_with_errors')

                    UNION ALL

                    SELECT
                        'scheduled_report_failures'::varchar,
                        'Scheduled Report Failures'::varchar,
                        'Reporting Operators'::varchar,
                        COUNT(*)::int,
                        COUNT(*) FILTER (WHERE consecutive_failure_count >= 2)::int,
                        COALESCE(MAX((CURRENT_DATE - COALESCE(last_failure_on::date, CURRENT_DATE))::int), 0)::int,
                        CASE
                            WHEN COUNT(*) FILTER (WHERE consecutive_failure_count >= 2) > 0 THEN 'blocked'
                            WHEN COUNT(*) > 0 THEN 'attention'
                            ELSE 'healthy'
                        END::varchar,
                        'Recurring report schedules whose latest generation attempt failed.'::text,
                        'sports_federation_reporting.action_federation_report_schedule'::varchar
                    FROM federation_report_schedule
                    WHERE last_run_status = 'failed'
                )
                SELECT
                    row_number() OVER (
                        ORDER BY
                            CASE status
                                WHEN 'blocked' THEN 3
                                WHEN 'attention' THEN 2
                                ELSE 1
                            END DESC,
                            open_count DESC,
                            queue_name ASC
                    ) AS id,
                    queue_code,
                    queue_name,
                    owner_display,
                    open_count,
                    escalated_count,
                    oldest_age_days,
                    status,
                    CASE status
                        WHEN 'blocked' THEN 3
                        WHEN 'attention' THEN 2
                        ELSE 1
                    END AS status_priority,
                    summary,
                    action_xmlid
                FROM queue_rows
            )
            """)
