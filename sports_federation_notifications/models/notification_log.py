import logging

from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.sports_federation_base.models.failure_feedback import (
    FAILURE_CATEGORY_SELECTION,
)

_logger = logging.getLogger(__name__)


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
    correlation_id = fields.Char(string="Correlation ID", index=True)
    attempt_count = fields.Integer(default=0, readonly=True)
    last_attempt_on = fields.Datetime(readonly=True)
    acknowledged = fields.Boolean(default=False)
    acknowledged_by_id = fields.Many2one("res.users", readonly=True)
    acknowledged_on = fields.Datetime(readonly=True)

    target_display_name = fields.Char(
        string="Target",
        compute="_compute_target_display_name",
    )

    @api.depends("target_model", "target_res_id")
    def _compute_target_display_name(self):
        """Resolve the display name of the target record, guarding for optional models."""
        for rec in self:
            if not rec.target_model or not rec.target_res_id:
                rec.target_display_name = False
                continue
            model = self.env.get(rec.target_model)
            if model is None:
                rec.target_display_name = rec.target_model
                continue
            try:
                record = model.sudo().browse(rec.target_res_id).exists()
                rec.target_display_name = record.display_name if record else False
            except Exception:  # integration boundary: optional target model
                _logger.exception(
                    "Could not resolve notification target %s,%s",
                    rec.target_model,
                    rec.target_res_id,
                )
                rec.target_display_name = False

    def action_acknowledge_failure(self):
        self.filtered(lambda log: log.state == "failed").write(
            {
                "acknowledged": True,
                "acknowledged_by_id": self.env.user.id,
                "acknowledged_on": fields.Datetime.now(),
            }
        )
        return True

    def action_view_target(self):
        """Return an act_window action to open the target record."""
        self.ensure_one()
        if not self.target_model or not self.target_res_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": self.target_model,
            "view_mode": "form",
            "res_id": self.target_res_id,
            "target": "current",
        }

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
    def _retention_candidate_count(self, reference_dt=None):
        reference_dt = fields.Datetime.to_datetime(
            reference_dt or fields.Datetime.now()
        )
        return sum(
            self.sudo().search_count(
                [
                    ("state", "=", state),
                    ("create_date", "!=", False),
                    (
                        "create_date",
                        "<",
                        fields.Datetime.to_string(reference_dt - timedelta(days=days)),
                    ),
                ]
            )
            for state, days in self.RETENTION_DAYS_BY_STATE.items()
        )

    @api.model
    def _cron_purge_old_logs(self):
        started_on = fields.Datetime.now()
        candidates = self._retention_candidate_count(started_on)
        Evidence = self.env["federation.retention.evidence"]
        try:
            deleted = self._purge_retained_logs(started_on)
        except Exception as error:
            Evidence.record_failure_durable(
                "notification_logs",
                started_on=started_on,
                candidate_count=candidates,
                failure_count=candidates or 1,
                retention_rules=self.RETENTION_DAYS_BY_STATE,
                operator_message=str(error),
                source_model=self._name,
            )
            raise
        Evidence.record_execution(
            "notification_logs",
            started_on=started_on,
            candidate_count=candidates,
            deleted_count=deleted,
            skipped_count=max(0, candidates - deleted),
            retention_rules=self.RETENTION_DAYS_BY_STATE,
            source_model=self._name,
        )
        return deleted
