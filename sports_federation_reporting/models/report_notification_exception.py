from odoo import fields, models, tools
from odoo.addons.sports_federation_base.models.failure_feedback import (
    FAILURE_CATEGORY_SELECTION,
)

from .report_operational import FederationReportOperational


class FederationReportNotificationException(models.Model):
    _name = "federation.report.notification.exception"
    _description = "Federation Notification Exception Report"
    _auto = False
    _order = "created_on desc, notification_log_id desc"

    NOTIFICATION_TYPE_SELECTION = [
        ("email", "Email"),
        ("activity", "Activity"),
        ("other", "Other"),
    ]

    STATE_SELECTION = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    notification_log_id = fields.Many2one(
        "federation.notification.log",
        string="Notification Log",
        readonly=True,
    )
    created_on = fields.Datetime(string="Created On", readonly=True)
    name = fields.Char(string="Name", readonly=True)
    target_model = fields.Char(string="Target Model", readonly=True)
    target_res_id = fields.Integer(string="Target Record ID", readonly=True)
    recipient_email = fields.Char(string="Recipient Email", readonly=True)
    notification_type = fields.Selection(
        NOTIFICATION_TYPE_SELECTION,
        string="Notification Type",
        readonly=True,
    )
    template_xmlid = fields.Char(string="Template XML ID", readonly=True)
    state = fields.Selection(STATE_SELECTION, string="State", readonly=True)
    failure_category = fields.Selection(
        FAILURE_CATEGORY_SELECTION, string="Failure Category", readonly=True
    )
    message = fields.Text(string="Failure Message", readonly=True)
    age_days = fields.Integer(string="Age (Days)", readonly=True)
    queue_owner_display = fields.Char(string="Queue Owner", readonly=True)
    sla_due_on = fields.Datetime(string="SLA Due On", readonly=True)
    sla_status = fields.Selection(
        FederationReportOperational.SLA_STATUS_SELECTION,
        string="SLA Status",
        readonly=True,
    )

    def init(self):
        """Rebuild the SQL view so failed-notification rows match the model schema."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_notification_exception AS (
                -- block: report_rows
                SELECT
                    log.id AS id,
                    log.id AS notification_log_id,
                    log.create_date AS created_on,
                    log.name,
                    log.target_model,
                    log.target_res_id,
                    log.recipient_email,
                    log.notification_type,
                    log.template_xmlid,
                    log.state,
                    log.failure_category,
                    COALESCE(log.operator_message, log.message) AS message,
                    (CURRENT_DATE - COALESCE(log.create_date::date, CURRENT_DATE))::int AS age_days,
                    'Federation Managers'::varchar AS queue_owner_display,
                    (COALESCE(log.create_date, NOW()) + INTERVAL '1 day') AS sla_due_on,
                    CASE
                        WHEN CURRENT_TIMESTAMP < (COALESCE(log.create_date, NOW()) + INTERVAL '1 day') THEN 'within_sla'
                        WHEN CURRENT_DATE = (COALESCE(log.create_date, NOW()) + INTERVAL '1 day')::date THEN 'due_today'
                        WHEN CURRENT_TIMESTAMP < (COALESCE(log.create_date, NOW()) + INTERVAL '3 day') THEN 'overdue'
                        ELSE 'escalated'
                    END AS sla_status
                FROM federation_notification_log log
                WHERE log.state = 'failed'
            )
            """)
