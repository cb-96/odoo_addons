"""Failure isolation, bounded inbox queries and coordinated mail retention."""
import logging
from datetime import timedelta

from psycopg2.errors import DeadlockDetected, SerializationFailure
from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.addons.sports_federation_base.models.failure_feedback import build_failure_feedback
from ..communication_policy import delivery_label

_logger = logging.getLogger(__name__)


class NotificationOperations(models.AbstractModel):
    _inherit = "federation.notification.service"

    def _run_notification_effect(self, callback, source=None, name="Notification",
                                 fallback_model="federation.notification.log"):
        """Rollback only notification work; framework transaction retries propagate.

        Failure evidence is best effort in a separate savepoint. A failed evidence
        write must not undo the business decision. No private exception text is
        copied to recipients, and no failure is represented as successful delivery.
        """
        try:
            with self.env.cr.savepoint():
                return callback()
        except (DeadlockDetected, SerializationFailure):
            raise
        except Exception as error:
            _logger.exception("Notification producer failed: %s", name)
            category, message = build_failure_feedback(error=error)
            log = self.env["federation.notification.log"].sudo().browse()
            try:
                with self.env.cr.savepoint():
                    log = log.create({
                        "name": name, "notification_type": "other", "state": "failed",
                        "target_model": source._name if source is not None else False,
                        "target_res_id": source[:1].id if source is not None and source else False,
                        "failure_category": category, "operator_message": message,
                    })
            except (DeadlockDetected, SerializationFailure):
                raise
            except Exception:
                _logger.exception("Could not persist notification failure evidence: %s", name)
                log = self.env["federation.notification.log"].sudo().browse()
            return log if fallback_model == "federation.notification.log" else self.env[fallback_model].browse()

    @api.model
    def _inbox_page(self, user, status="all", before=0, limit=20):
        """Scan at most 200 candidates and return at most 20 authorized items.

        Cursor follows the last scanned row, including invisible rows. An empty
        page may have a continuation; it must not imply that no older work exists.
        """
        if user != self.env.user:
            raise AccessError(_("Only your own notification inbox is available."))
        limit = max(1, min(20, int(limit)))
        before = max(0, int(before))
        domain = [("recipient_id", "=", user.id), ("superseded_on", "=", False)]
        if status == "acknowledged":
            domain.append(("acknowledged_on", "!=", False))
        elif status == "unacknowledged":
            domain.append(("acknowledged_on", "=", False))
        if before:
            domain.append(("id", "<", before))
        candidates = self.env["federation.communication.receipt"].search(domain, order="id desc", limit=200)
        items = []
        cursor = False
        for receipt in candidates:
            cursor = receipt.id
            try:
                info = receipt._presentation(user)
            except AccessError:
                continue
            items.append({"receipt": receipt, "info": info,
                          "deliveries": [(delivery, _(delivery_label(delivery.state)))
                                         for delivery in receipt.delivery_ids]})
            if len(items) == limit:
                break
        # A full candidate window or a full visible page can have older records.
        more = bool(cursor and (len(candidates) == 200 or len(items) == limit)
                    and self.env["federation.communication.receipt"].search(
                        domain + [("id", "<", cursor)], order="id desc", limit=1))
        return {"items": items, "next_before": cursor if more else False}


class NotificationLogRetention(models.Model):
    _inherit = "federation.notification.log"

    def _retention_deletable(self, allow_cancelled=False):
        """Keep shared/open delivery evidence and pending/cancelled-review mail."""
        deliveries = self.env["federation.communication.delivery"].sudo().search([
            ("log_id", "in", self.ids),
        ])
        protected = set(deliveries.mapped("log_id").ids)
        return self.filtered(lambda log: log.id not in protected
                             and (not log.mail_id or log.mail_id.state == "sent"
                                  or (allow_cancelled and log.mail_id.state == "cancel")))



    @api.model
    def _cron_purge_old_logs(self):
        deleted = super()._cron_purge_old_logs()
        self._cron_purge_owned_mail()
        return deleted

    @api.model
    def _cron_purge_owned_mail(self):
        """Retry terminal orphan cleanup, including previously locked records."""
        started = fields.Datetime.now()
        evidence = self.env["federation.retention.evidence"]
        rules = {"minimum_age_days": 90, "owned_only": True, "batch_limit": 200}
        try:
            with self.env.cr.savepoint():
                self.env.flush_all()
                self.env.cr.execute("""
                    SELECT mail.id FROM mail_mail AS mail
                     WHERE mail.federation_notification_owned = TRUE
                       AND mail.state IN ('sent', 'cancel')
                       AND mail.create_date < %s
                       AND NOT EXISTS (SELECT 1 FROM federation_notification_log AS log
                                       WHERE log.mail_id = mail.id)
                       AND NOT EXISTS (SELECT 1 FROM federation_communication_delivery AS delivery
                                       WHERE delivery.mail_id = mail.id)
                     ORDER BY mail.create_date, mail.id LIMIT 200
                """, [started - timedelta(days=90)])
                ids = [row[0] for row in self.env.cr.fetchall()]
                deleted = self.env["mail.mail"].browse(ids)._purge_notification_orphans()
        except (DeadlockDetected, SerializationFailure):
            raise
        except Exception as error:
            evidence.record_failure_durable(
                "notification_mail_content", started_on=started, failure_count=1,
                retention_rules=rules, operator_message=str(error), source_model="mail.mail",
            )
            raise
        evidence.record_execution(
            "notification_mail_content", started_on=started, candidate_count=len(ids),
            deleted_count=deleted, skipped_count=len(ids) - deleted,
            retention_rules=rules, source_model="mail.mail",
        )
        return deleted


class NotificationMailRetention(models.Model):
    _inherit = "mail.mail"

    def _purge_notification_orphans(self):
        """Only explicitly owned terminal mail, with no log/delivery reference.

        Never sweep unrelated mail or pending/failed mail. Historical unmarked
        mail is not guessed to be owned; migration marks only linked records.
        """
        count = 0
        for mail in self.sudo().exists():
            if not mail.federation_notification_owned or mail.state not in ("sent", "cancel"):
                continue
            self.env.cr.execute("SELECT id FROM mail_mail WHERE id = %s FOR UPDATE SKIP LOCKED", [mail.id])
            if not self.env.cr.fetchone():
                continue
            mail.invalidate_recordset()
            if mail.state not in ("sent", "cancel"):
                continue
            if self.env["federation.notification.log"].sudo().search_count([("mail_id", "=", mail.id)]):
                continue
            if self.env["federation.communication.delivery"].sudo().search_count([("mail_id", "=", mail.id)]):
                continue
            mail.unlink()
            count += 1
        return count


class NotificationReceiptIndex(models.Model):
    _inherit = "federation.communication.receipt"

    def init(self):
        result = super().init()
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS federation_receipt_recipient_cursor_idx
                ON federation_communication_receipt (recipient_id, id DESC)
                WHERE superseded_on IS NULL
        """)
        return result
