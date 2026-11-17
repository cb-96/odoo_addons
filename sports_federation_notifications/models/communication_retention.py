"""Retention for participant inbox receipts and their outbound deliveries.

Nothing is deleted until the federation configures a retention period in
``sports_federation_notifications.inbox_retention_days``. Only closed inbox
items (acted upon, expired or superseded) whose closing date is older than the
period are removed, and never while one of their deliveries still needs
attention. Deliveries are removed once they are finished and no inbox item
refers to them any more. Every run records retention evidence.
"""

from datetime import timedelta

from odoo import api, fields, models

from .. import communication_policy as policy

from odoo.addons.sports_federation_base.batch_jobs import for_each_chunk

RETENTION_PARAMETER = "sports_federation_notifications.inbox_retention_days"
RETENTION_POLICY_CODE = "participant_inbox"
# Receipts also enforce one notification per event and recipient. Keeping
# closed items for at least this long prevents a late re-emitted event from
# notifying the same person twice.
MIN_RETENTION_DAYS = 30
OPEN_DELIVERY_STATES = ("pending", "queued", "failed")
FINISHED_DELIVERY_STATES = ("sent", "cancelled", "suppressed")


def retention_days_from_value(value):
    """Return ``(days, problem)`` for a configured parameter value.

    ``days`` is ``0`` when retention is disabled or misconfigured; ``problem``
    explains a misconfiguration and is ``False`` otherwise.
    """
    if value in (None, False, ""):
        return 0, False
    try:
        days = int(value)
    except (TypeError, ValueError):
        return 0, "Inbox retention period %r is not a whole number of days." % (value,)
    if days <= 0:
        return 0, False
    if days < MIN_RETENTION_DAYS:
        return 0, (
            "Inbox retention period %s is below the minimum of %s days; "
            "nothing was deleted." % (days, MIN_RETENTION_DAYS)
        )
    return days, False


class CommunicationReceiptRetention(models.Model):
    _inherit = "federation.communication.receipt"

    @api.model
    def _inbox_retention_days(self):
        value = self.env["ir.config_parameter"].sudo().get_param(RETENTION_PARAMETER)
        return retention_days_from_value(value)

    @api.model
    def _inbox_retention_domain(self, cutoff):
        cutoff = fields.Datetime.to_string(cutoff)
        return [
            ("lifecycle_state", "in", policy.CLOSED_LIFECYCLE),
            "|",
            "|",
            ("acted_on", "<", cutoff),
            ("expired_on", "<", cutoff),
            ("superseded_on", "<", cutoff),
        ]

    @api.model
    def _inbox_retention_candidates(self, cutoff):
        receipts = self.sudo().search(self._inbox_retention_domain(cutoff))
        # An item whose delivery still needs attention (waiting, queued or
        # failed) is unresolved work and is always kept.
        return receipts.filtered(
            lambda receipt: not any(
                state in OPEN_DELIVERY_STATES
                for state in receipt.delivery_ids.mapped("state")
            )
        )

    @api.model
    def _purge_retained_inbox(self, reference_dt=None):
        """Delete closed inbox items and finished deliveries past the period.

        Returns a dict with the counts used for retention evidence.
        """
        days, problem = self._inbox_retention_days()
        result = {
            "days": days,
            "problem": problem,
            "candidates": 0,
            "receipts": 0,
            "deliveries": 0,
        }
        if not days:
            return result
        reference_dt = fields.Datetime.to_datetime(
            reference_dt or fields.Datetime.now()
        )
        cutoff = reference_dt - timedelta(days=days)
        receipts = self._inbox_retention_candidates(cutoff)
        result["candidates"] = len(receipts)
        result["receipts"] = len(receipts)
        result["deliveries"] = for_each_chunk(receipts, self._purge_inbox_chunk)
        return result

    @api.model
    def _purge_inbox_chunk(self, receipts):
        """Delete one batch of receipts and the deliveries they leave behind."""
        deliveries = receipts.mapped("delivery_ids")
        receipts.unlink()
        Delivery = self.env["federation.communication.delivery"].sudo()
        orphaned = Delivery.search(
            [
                ("id", "in", deliveries.ids),
                ("state", "in", FINISHED_DELIVERY_STATES),
                ("receipt_ids", "=", False),
            ]
        )
        count = len(orphaned)
        mails = orphaned.mapped("mail_id")
        logs = orphaned.mapped("log_id")
        orphaned.unlink()
        logs._retention_deletable(allow_cancelled=True).unlink()
        mails._purge_notification_orphans()
        return count

    @api.model
    def _cron_purge_inbox(self):
        started_on = fields.Datetime.now()
        Evidence = self.env["federation.retention.evidence"]
        days, problem = self._inbox_retention_days()
        rules = {
            "parameter": RETENTION_PARAMETER,
            "days": days,
            "minimum_days": MIN_RETENTION_DAYS,
            "closed_states": list(policy.CLOSED_LIFECYCLE),
        }
        try:
            result = self._purge_retained_inbox(started_on)
        except Exception as error:
            Evidence.record_failure_durable(
                RETENTION_POLICY_CODE,
                started_on=started_on,
                failure_count=1,
                retention_rules=rules,
                operator_message=str(error),
                source_model=self._name,
            )
            raise
        if problem:
            message = problem
        elif not days:
            message = "No inbox retention period is configured; all items are kept."
        else:
            message = "Deleted %s inbox item(s) and %s finished delivery record(s)." % (
                result["receipts"],
                result["deliveries"],
            )
        Evidence.record_execution(
            RETENTION_POLICY_CODE,
            started_on=started_on,
            candidate_count=result["candidates"],
            deleted_count=result["receipts"] + result["deliveries"],
            failure_count=1 if problem else 0,
            status="failed" if problem else "passed",
            dry_run=not days,
            retention_rules=rules,
            operator_message=message,
            source_model=self._name,
        )
        return result
