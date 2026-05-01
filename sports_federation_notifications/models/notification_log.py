from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.sports_federation_base.models.failure_feedback import (
    FAILURE_CATEGORY_SELECTION,
)


class FederationNotificationLog(models.Model):
    _name = "federation.notification.log"
    _description = "Federation Notification Log"
    _order = "create_date desc"

    RETENTION_DAYS_BY_STATE = {
        "pending": 30,
        "sent": 90,
        "failed": 180,
    }

    name = fields.Char(string="Name", required=True)
    target_model = fields.Char(string="Target Model")
    target_res_id = fields.Integer(string="Target Record ID")
    recipient_partner_id = fields.Many2one(
        "res.partner",
        string="Recipient Partner",
        ondelete="set null",
    )
    recipient_email = fields.Char(string="Recipient Email")
    notification_type = fields.Selection(
        [
            ("email", "Email"),
            ("activity", "Activity"),
            ("other", "Other"),
        ],
        string="Notification Type",
        required=True,
    )
    template_xmlid = fields.Char(string="Template XML ID")
    sent_on = fields.Datetime(string="Sent On")
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("sent", "Sent"),
            ("failed", "Failed"),
        ],
        string="State",
        default="pending",
        required=True,
    )
    failure_category = fields.Selection(
        FAILURE_CATEGORY_SELECTION, string="Failure Category"
    )
    operator_message = fields.Text(string="Operator Message")
    message = fields.Text(string="Message")

    @api.model
    def _cron_notification_scan(self):
        """Delegate to the notification service cron method."""
        self.env[
            "federation.notification.service"
        ]._cron_placeholder_notification_scan()

    @api.model
    def _purge_retained_logs(self, reference_dt=None):
        """Delete notification logs that exceeded the policy for their state."""
        reference_dt = fields.Datetime.to_datetime(
            reference_dt or fields.Datetime.now()
        )
        total_deleted = 0
        for state, days in self.RETENTION_DAYS_BY_STATE.items():
            cutoff = fields.Datetime.to_string(reference_dt - timedelta(days=days))
            logs = self.sudo().search(
                [
                    ("state", "=", state),
                    ("create_date", "!=", False),
                    ("create_date", "<", cutoff),
                ]
            )
            total_deleted += len(logs)
            logs.unlink()
        return total_deleted

    @api.model
    def _cron_purge_old_logs(self):
        """Execute the notification-log retention policy."""
        return self._purge_retained_logs()
