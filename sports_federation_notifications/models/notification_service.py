from .notification_boundary import notification_effect
import logging
from psycopg2.errors import DeadlockDetected, SerializationFailure

from odoo import api, fields, models
from odoo.addons.sports_federation_base.correlation import ensure_correlation_id
from odoo.addons.sports_federation_base.models.failure_feedback import (
    build_failure_feedback,
)

_logger = logging.getLogger(__name__)


class FederationNotificationService(models.AbstractModel):
    """Abstract service providing reusable notification helpers.

    Implemented as AbstractModel so it can be inherited by other modules
    without creating a concrete table. This keeps the service lightweight
    and allows future extensions.
    """

    _name = "federation.notification.service"
    _description = "Federation Notification Service"

    @notification_effect()
    def send_email_template(
        self, record, template_xmlid, partner=None, email_to=None, log_name=None
    ):
        """Persist a delivery intent and queue mail; never contact SMTP here."""
        if isinstance(email_to, (list, tuple, set)):
            email_to = ",".join(dict.fromkeys(email for email in email_to if email))
        log = (
            self.env["federation.notification.log"]
            .sudo()
            .create(
                {
                    "name": log_name or "Email: %s" % template_xmlid,
                    "target_model": record._name,
                    "target_res_id": record.id,
                    "notification_type": "email",
                    "template_xmlid": template_xmlid,
                    "recipient_partner_id": (
                        partner.id if partner and partner.exists() else False
                    ),
                    "recipient_email": (
                        partner.email if partner and partner.exists() else email_to
                    ),
                    "correlation_id": ensure_correlation_id(self.env),
                }
            )
        )
        if partner and not partner.exists():
            log._queue_failed(
                ValueError("Recipient partner is missing or has been deleted.")
            )
            return log
        return self._queue_template(log, record, partner=partner, email_to=email_to)

    def _queue_template(self, log, record, partner=None, email_to=None):
        """Render in a savepoint; a render failure must not undo the decision."""
        try:
            with self.env.cr.savepoint():
                template = self.env.ref(log.template_xmlid, raise_if_not_found=False)
                if not template:
                    raise ValueError(
                        "Template '%s' is not available in this database."
                        % log.template_xmlid
                    )
                values = {"auto_delete": False, "federation_notification_owned": True}
                if partner:
                    values.update(recipient_ids=[(6, 0, [partner.id])], email_to=False)
                elif email_to:
                    values.update(email_to=email_to, recipient_ids=[(5, 0, 0)])
                mail_id = template.sudo().send_mail(
                    record.id,
                    force_send=False,
                    email_values=values,
                )
                mail = self.env["mail.mail"].sudo().browse(mail_id).exists()
                if not mail:
                    raise ValueError("Template did not create an outbound mail record.")
                log._queued(mail)
        except (DeadlockDetected, SerializationFailure):
            raise
        except Exception as error:
            log._queue_failed(error)
        return log

    @notification_effect()
    def queue_direct_email(self, record, subject, body_html, email_to, log_name=None):
        """Direct-content fallback uses the same mail queue and delivery evidence."""
        log = (
            self.env["federation.notification.log"]
            .sudo()
            .create(
                {
                    "name": log_name or subject,
                    "target_model": record._name,
                    "target_res_id": record.id,
                    "notification_type": "email",
                    "recipient_email": email_to,
                    "correlation_id": ensure_correlation_id(self.env),
                }
            )
        )
        try:
            with self.env.cr.savepoint():
                mail = (
                    self.env["mail.mail"]
                    .sudo()
                    .create(
                        {
                            "subject": subject,
                            "body_html": body_html,
                            "email_to": email_to,
                            "email_from": (
                                self.env.company.partner_id.email_formatted
                                or self.env.user.email_formatted
                                or False
                            ),
                            "auto_delete": False,
                            "federation_notification_owned": True,
                        }
                    )
                )
                log._queued(mail)
        except (DeadlockDetected, SerializationFailure):
            raise
        except Exception as error:
            log._queue_failed(error)
        return log

    @notification_effect()
    def create_activity(
        self,
        record,
        user_id,
        summary,
        note=None,
        activity_type_xmlid="mail.mail_activity_data_todo",
    ):
        """Create a mail.activity and log it.

        Args:
            record: The target record for the activity.
            user_id: The res.users ID to assign the activity to.
            summary: Activity summary string.
            note: Optional HTML note.
            activity_type_xmlid: XML ID for activity type (default: todo).

        Returns:
            The created notification log record.
        """
        Log = self.env["federation.notification.log"].sudo()
        correlation_id = ensure_correlation_id(self.env)
        activity_type = self.env.ref(activity_type_xmlid, raise_if_not_found=False)

        log_vals = {
            "name": summary,
            "target_model": record._name,
            "target_res_id": record.id,
            "notification_type": "activity",
            "state": "pending",
            "correlation_id": correlation_id,
        }

        log = Log.create(log_vals)

        try:
            with self.env.cr.savepoint():
                self.env["mail.activity"].sudo().create(
                    {
                        "res_model_id": self.env["ir.model"]._get_id(record._name),
                        "res_id": record.id,
                        "activity_type_id": (
                            activity_type.id if activity_type else False
                        ),
                        "summary": summary,
                        "note": note or "",
                        "user_id": user_id,
                    }
                )
                log.write(
                    {
                        "state": "sent",
                        "sent_on": fields.Datetime.now(),
                        "failure_category": False,
                        "operator_message": False,
                    }
                )
        except (DeadlockDetected, SerializationFailure):
            raise
        except Exception as e:
            failure_category, operator_message = build_failure_feedback(error=e)
            _logger.exception(
                "Notification activity creation failed for %s (correlation_id=%s)",
                log.display_name,
                correlation_id,
            )
            log.write(
                {
                    "state": "failed",
                    "failure_category": failure_category,
                    "operator_message": operator_message,
                    "message": False,
                }
            )

        return log

    @api.model
    def _cron_placeholder_notification_scan(self):
        """Default cron scan for stale registrations and officiating gaps.

        The scan logs draft season-registration reminders and, when the related
        modules are installed, creates activities for overdue referee
        confirmations and officiating shortages.
        """
        Log = self.env["federation.notification.log"].sudo()
        correlation_id = ensure_correlation_id(self.env)
        Registration = self.env.get("federation.season.registration")

        if not Registration:
            Log.create(
                {
                    "name": "Cron: Notification Scan",
                    "notification_type": "other",
                    "state": "sent",
                    "sent_on": fields.Datetime.now(),
                    "message": "No federation.season.registration model found. No action configured.",
                    "correlation_id": correlation_id,
                }
            )
            return

        # Search for draft registrations older than 7 days
        from datetime import timedelta

        cutoff_date = fields.Datetime.now() - timedelta(days=7)
        old_drafts = Registration.search(
            [
                ("state", "=", "draft"),
                ("create_date", "<", cutoff_date),
            ],
            limit=20,
        )

        if old_drafts:
            for reg in old_drafts:
                Log.create(
                    {
                        "name": f"Draft registration reminder: {reg.name or reg.id}",
                        "target_model": "federation.season.registration",
                        "target_res_id": reg.id,
                        "notification_type": "other",
                        "state": "sent",
                        "sent_on": fields.Datetime.now(),
                        "message": f"Season registration '{reg.name}' has been in draft state for more than 7 days.",
                        "correlation_id": correlation_id,
                    }
                )
        else:
            Log.create(
                {
                    "name": "Cron: Notification Scan",
                    "notification_type": "other",
                    "state": "sent",
                    "sent_on": fields.Datetime.now(),
                    "message": "No draft registrations older than 7 days found.",
                    "correlation_id": correlation_id,
                }
            )

        Dispatcher = self.env.get("federation.notification.dispatcher")
        MatchReferee = self.env.get("federation.match.referee")
        Match = self.env.get("federation.match")

        if Dispatcher is not None and MatchReferee:
            overdue_assignments = MatchReferee.search(
                [
                    ("state", "=", "draft"),
                ],
                limit=20,
            ).filtered(lambda assignment: assignment.is_confirmation_overdue)
            for assignment in overdue_assignments:
                Dispatcher.send_referee_confirmation_overdue(assignment)

        if Dispatcher is not None and Match and "is_officially_ready" in Match._fields:
            shortage_matches = Match.search(
                [
                    ("state", "in", ("draft", "scheduled")),
                    ("date_scheduled", "!=", False),
                ],
                limit=20,
            ).filtered(
                lambda match: match.required_referee_count
                and not match.is_officially_ready
            )
            for match in shortage_matches:
                Dispatcher.send_referee_shortage_alert(match)
