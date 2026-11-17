from markupsafe import Markup, escape
from odoo import _, fields, models
from odoo.exceptions import AccessError
from .actionable_communications import _lock


class CommunicationMail(models.Model):
    _inherit = "mail.mail"

    federation_notification_owned = fields.Boolean(
        default=False, copy=False, index=True
    )

    def send(self, *args, **kwargs):
        # Last responsible moment: queue creation does not freeze permissions or preferences.
        deliveries = (
            self.env["federation.communication.delivery"]
            .sudo()
            .search([("mail_id", "in", self.ids)])
        )
        blocked = self.browse()
        for delivery in deliveries:
            _lock(self.env, "delivery:%s" % delivery.id)
            user = delivery.recipient_id
            valid = delivery.receipt_ids.browse()
            for receipt in delivery.receipt_ids:
                try:
                    info = receipt._presentation(user)
                    mode = self.env["federation.communication.preference"]._mode_for(
                        user, receipt.kind
                    )
                    if mode == "digest" and not delivery.delivery_key.startswith(
                        "digest:"
                    ):
                        delivery.write({"receipt_ids": [(3, receipt.id)]})
                        continue
                    if (
                        mode != "inbox"
                        and not info.get("complete")
                        and not (receipt.kind == "due_soon" and receipt.acknowledged_on)
                    ):
                        valid |= receipt
                except AccessError:
                    continue
            if not user.active or not valid or not user.partner_id.email:
                delivery.mail_id.write({"state": "cancel"})
                delivery.write({"state": "cancelled"})
                blocked |= delivery.mail_id
                continue
            base = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("web.base.url", "")
                .rstrip("/")
            )
            links = Markup("").join(
                Markup('<li><a href="%s/my/notifications/%s">%s</a></li>')
                % (escape(base), receipt.id, escape(receipt.name))
                for receipt in valid
            )
            delivery.mail_id.write(
                {
                    "email_to": user.partner_id.email,
                    "recipient_ids": [(5, 0, 0)],
                    "body_html": Markup(
                        "<p>Review your current federation work:</p><ul>%s</ul>"
                    )
                    % links,
                }
            )
        sendable = self - blocked
        logs = (
            self.env["federation.notification.log"]
            .sudo()
            .search(
                [
                    ("mail_id", "in", sendable.ids),
                    ("mail_id.state", "=", "outgoing"),
                    ("target_model", "!=", "federation.communication.delivery"),
                ]
            )
        )
        if logs:
            self.env.cr.execute(
                "SELECT id FROM mail_mail WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                [sendable.ids],
            )
        for log in logs:
            log.write(
                {
                    "attempt_count": log.attempt_count + 1,
                    "last_attempt_on": fields.Datetime.now(),
                }
            )
        try:
            result = (
                super(CommunicationMail, sendable).send(*args, **kwargs)
                if sendable
                else True
            )
        finally:
            # Mail state is the evidence; queuing is never reported as sent.
            for log in logs:
                log._reconcile_mail()
        for delivery in deliveries:
            delivery.mail_id.invalidate_recordset(["state"])
            if delivery.mail_id.state == "sent":
                delivery._accepted()
            elif delivery.mail_id.state == "exception":
                delivery._fail(
                    _(
                        "Outbound mail failed. Inspect the mail server error in the backend."
                    )
                )
        return result
