from odoo import _, models
from odoo.exceptions import AccessError, ValidationError


class FederationNotificationJobReliability(models.Model):
    _inherit = "federation.notification.log"

    def action_queue_retry(self):
        if not self.env.user.has_group("sports_federation_base.group_federation_manager"):
            raise AccessError(_("Only federation managers can retry notifications."))
        self.check_access("write")
        for log in self:
            if log.state != "failed":
                raise ValidationError(_("Only failed notifications can be retried."))
            if log.target_model == "federation.communication.delivery":
                delivery = self.env[log.target_model].browse(log.target_res_id).exists()
                if not delivery:
                    raise ValidationError(_("The delivery no longer exists."))
                delivery.action_retry_delivery()
            else:
                log.sudo()._retry_queued_email()
        return True

    def _retry_operational_job(self, job):
        """Compatibility for already persisted jobs: success means queued, not sent."""
        self.ensure_one()
        if self.state == "sent" or (self.mail_id and self.mail_id.state == "outgoing"):
            return True
        if self.target_model == "federation.communication.delivery":
            self.env[self.target_model].browse(self.target_res_id).action_retry_delivery()
        else:
            self._retry_queued_email()
        if self.state == "failed":
            raise RuntimeError(self.operator_message or _("Notification could not be queued."))
        return True
