"""Delivery evidence and retry scheduling around the existing Odoo mail queue.

No SMTP transport lives here. Actionable communication deliveries retain their
permission-aware retry owner; ordinary event mail uses this log as its owner.
"""
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.addons.sports_federation_base.models.failure_feedback import build_failure_feedback

_logger = logging.getLogger(__name__)
MAX_AUTOMATIC_ATTEMPTS = 3


class NotificationOutbox(models.Model):
    _inherit = "federation.notification.log"

    mail_id = fields.Many2one("mail.mail", readonly=True, copy=False,
                             ondelete="set null", index=True)
    queued_on = fields.Datetime(readonly=True, copy=False)
    next_attempt_on = fields.Datetime(readonly=True, copy=False, index=True)
    outbox_checked_on = fields.Datetime(readonly=True, copy=False, index=True,
                                        default=fields.Datetime.now)

    def _queued(self, mail):
        self.ensure_one()
        self.write({
            "mail_id": mail.id, "queued_on": fields.Datetime.now(),
            "state": "pending", "sent_on": False, "next_attempt_on": False,
            "failure_category": False, "operator_message": False,
            "acknowledged": False,
        })

    def _queue_failed(self, error):
        self.ensure_one()
        category, message = build_failure_feedback(error=error)
        _logger.exception("Notification queue failed log=%s correlation_id=%s",
                          self.id, self.correlation_id)
        self.write({"state": "failed", "failure_category": category,
                    "operator_message": message, "next_attempt_on": False})

    def _reconcile_mail(self):
        self.ensure_one()
        mail = self.mail_id.exists()
        if not mail:
            if self.queued_on and self.state != "sent":
                self.write({"state": "failed", "next_attempt_on": False,
                            "failure_category": "data_validation",
                            "operator_message": _("Queued mail is missing. Verify delivery before recreating it.")})
            return
        mail.invalidate_recordset(["state", "failure_reason"])
        if mail.state == "sent":
            if self.state != "sent":
                self.write({"state": "sent", "sent_on": fields.Datetime.now(),
                            "failure_category": False, "operator_message": False,
                            "next_attempt_on": False})
        elif mail.state in ("exception", "cancel"):
            if self.state != "failed":
                category, message = build_failure_feedback(
                    error=RuntimeError(mail.failure_reason or "Outbound mail failed or was cancelled."))
                retry_on = False
                if (mail.state == "exception" and category == "retryable_delivery"
                        and self.attempt_count < MAX_AUTOMATIC_ATTEMPTS):
                    retry_on = fields.Datetime.now() + timedelta(minutes=5 * max(1, self.attempt_count))
                self.write({
                    "state": "failed", "failure_category": category,
                    "operator_message": message,
                    "next_attempt_on": retry_on,
                })

    def _lock_outbox(self):
        """Lock mail before log, matching the transport's update order."""
        self.ensure_one()
        if self.mail_id:
            self.env.cr.execute("SELECT id FROM mail_mail WHERE id = %s FOR UPDATE SKIP LOCKED",
                                [self.mail_id.id])
            if not self.env.cr.fetchone():
                return False
        self.env.cr.execute(
            "SELECT id FROM federation_notification_log WHERE id = %s FOR UPDATE SKIP LOCKED",
            [self.id],
        )
        if not self.env.cr.fetchone():
            return False
        self.invalidate_recordset()
        return True

    def _retry_queued_email(self):
        """Requeue the same mail/log; never recreate previously queued mail."""
        self.ensure_one()
        if self.notification_type != "email":
            raise ValidationError(_("Only email notifications use the outbound queue."))
        if not self._lock_outbox():
            raise ValidationError(_("Delivery is being processed. Retry after processing finishes."))
        if self.state == "sent":
            return True
        mail = self.mail_id.exists()
        if mail:
            mail.invalidate_recordset(["state"])
            if mail.state == "sent":
                self._reconcile_mail()
                return True
            if mail.state == "cancel":
                raise ValidationError(_("Cancelled mail requires operator review, not automatic requeueing."))
            if mail.state != "outgoing":
                mail.write({"state": "outgoing", "failure_reason": False,
                            "scheduled_date": False})
            self._queued(mail)
            return True
        if self.queued_on:
            raise ValidationError(_("Previously queued mail is missing. Verify delivery before recreating it."))
        if not self.template_xmlid:
            raise ValidationError(_("No queued content exists. Recreate this notification manually."))
        model = self.env.get(self.target_model)
        target = model.browse(self.target_res_id).exists() if model is not None else False
        if not target:
            raise ValidationError(_("The notification target no longer exists."))
        self.env["federation.notification.service"]._queue_template(
            self, target, partner=self.recipient_partner_id or None,
            email_to=self.recipient_email if not self.recipient_partner_id else None,
        )
        return self.state == "pending"

    @api.model
    def _cron_reconcile_outbox(self):
        """Reconcile bounded batches; requeue due failures without sending SMTP."""
        logs = self.sudo().search([
            ("notification_type", "=", "email"),
            ("target_model", "!=", "federation.communication.delivery"),
            ("state", "in", ("pending", "failed")),
            ("queued_on", "!=", False),
        ], order="outbox_checked_on asc, id", limit=200)
        for log in logs:
            try:
                with self.env.cr.savepoint():
                    if not log._lock_outbox():
                        continue
                    log.write({"outbox_checked_on": fields.Datetime.now()})
                    log._reconcile_mail()
                    if (log.state == "failed" and log.next_attempt_on
                            and log.next_attempt_on <= fields.Datetime.now()
                            and log.attempt_count < MAX_AUTOMATIC_ATTEMPTS):
                        log._retry_queued_email()
            except Exception:
                _logger.exception("Outbox reconciliation failed log=%s correlation_id=%s",
                                  log.id, log.correlation_id)
        return True
