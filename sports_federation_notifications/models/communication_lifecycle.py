import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError, ValidationError

from .. import communication_policy as policy

_logger = logging.getLogger(__name__)
EXPIRY_PARAMETER = "federation.notification_expiry_days"


class CommunicationReceiptLifecycle(models.Model):
    """Closes the loop: did the participant actually resolve what we asked?

    The lifecycle is derived from facts that already exist (deliveries,
    acknowledgement, supersession) plus three stamps written here: when the item
    was opened, when its requirement was found resolved, and when it expired.
    """

    _inherit = "federation.communication.receipt"

    seen_on = fields.Datetime(readonly=True, copy=False)
    acted_on = fields.Datetime(readonly=True, copy=False)
    expired_on = fields.Datetime(readonly=True, copy=False)
    expires_on = fields.Datetime(
        index=True,
        copy=False,
        help="Optional. Without a value the item expires after the configured number of days.",
    )
    lifecycle_checked_on = fields.Datetime(readonly=True, copy=False, index=True)
    lifecycle_state = fields.Selection(
        [(code, label) for code, label in policy.LIFECYCLE],
        compute="_compute_lifecycle_state",
        store=True,
        index=True,
        help="Delivered means accepted by the mail server or available in the inbox. "
        'Only "Acted upon" means the underlying requirement was resolved.',
    )

    @api.depends(
        "superseded_on",
        "acted_on",
        "expired_on",
        "seen_on",
        "acknowledged_on",
        "delivery_ids.state",
    )
    def _compute_lifecycle_state(self):
        for receipt in self:
            receipt.lifecycle_state = policy.lifecycle_state(
                superseded=bool(receipt.superseded_on),
                acted=bool(receipt.acted_on),
                expired=bool(receipt.expired_on),
                seen=bool(receipt.seen_on or receipt.acknowledged_on),
                delivery_states=receipt.delivery_ids.mapped("state"),
            )

    # ------------------------------------------------------------------
    # Seen
    # ------------------------------------------------------------------

    def mark_seen(self, user=None):
        """Record the first time the recipient opened the item."""
        user = user or self.env.user
        now = fields.Datetime.now()
        for receipt in self.filtered(
            lambda item: not item.seen_on and item.recipient_id == user
        ):
            receipt.sudo().write({"seen_on": now})
        return True

    # ------------------------------------------------------------------
    # Resolved or expired
    # ------------------------------------------------------------------

    def _expiry_days(self):
        value = self.env["ir.config_parameter"].sudo().get_param(EXPIRY_PARAMETER)
        try:
            days = int(value)
        except (TypeError, ValueError):
            return policy.DEFAULT_EXPIRY_DAYS
        return days if days > 0 else policy.DEFAULT_EXPIRY_DAYS

    def _reconcile_lifecycle(self, now, days):
        """Stamp one open item as acted upon or expired when the facts say so."""
        self.ensure_one()
        values = {"lifecycle_checked_on": now}
        try:
            info = self._presentation(self.recipient_id)
        except (AccessError, MissingError, ValidationError):
            info = None
        if info and info.get("complete"):
            values["acted_on"] = now
        else:
            deadline = self.expires_on or (self.available_on + timedelta(days=days))
            if deadline <= now:
                values["expired_on"] = now
        self.sudo().write(values)
        return values

    @api.model
    def _cron_reconcile_lifecycle(self, batch=200):
        """Reconcile open items, least recently checked first."""
        now = fields.Datetime.now()
        days = self.env["federation.communication.receipt"]._expiry_days()
        receipts = self.sudo().search(
            [("lifecycle_state", "not in", policy.CLOSED_LIFECYCLE)],
            order="lifecycle_checked_on asc nulls first, id asc",
            limit=batch,
        )
        for receipt in receipts:
            try:
                with self.env.cr.savepoint():
                    receipt._reconcile_lifecycle(now, days)
            except Exception:  # pylint: disable=broad-except
                _logger.exception(
                    "Notification lifecycle check failed for receipt %s", receipt.id
                )
        return len(receipts)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @api.model
    def lifecycle_report(self, domain=None):
        """Counts per kind and state, and how often requirements got resolved."""
        rows = self._read_group(domain or [], ["kind", "lifecycle_state"], ["__count"])
        return policy.summarize_lifecycle(
            [(kind, state, count) for kind, state, count in rows]
        )
