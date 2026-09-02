from odoo import _, models
from odoo.exceptions import ValidationError


class FederationNotificationJobReliability(models.Model):
    _inherit = "federation.notification.log"

    def action_queue_retry(self):
        for log in self:
            if log.state != "failed":
                raise ValidationError(_("Only failed notifications can be retried."))
            job = self.env["federation.operation.job"].ensure_job(
                log,
                log.correlation_id or f"notification-{log.id}",
                name=f"Retry notification: {log.name}",
            )
            if job.state in ("done", "operator_action"):
                job.action_retry()
        return True

    def _retry_operational_job(self, job):
        self.ensure_one()
        if self.notification_type != "email" or not self.template_xmlid:
            raise ValidationError(_("This notification requires manual recreation."))
        model = self.env.get(self.target_model)
        target = model.browse(self.target_res_id).exists() if model is not None else model
        if not target:
            raise ValidationError(_("The notification target no longer exists."))
        retried = self.env["federation.notification.service"].send_email_template(
            target,
            self.template_xmlid,
            partner=self.recipient_partner_id or None,
            email_to=self.recipient_email if not self.recipient_partner_id else None,
            log_name=f"Retry: {self.name}",
        )
        if retried.state != "sent":
            raise RuntimeError(retried.operator_message or _("Notification retry failed."))
        self.write({"state": "sent", "failure_category": False, "operator_message": False})
        return True
