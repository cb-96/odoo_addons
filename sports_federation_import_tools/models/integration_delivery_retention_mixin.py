from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.sports_federation_import_tools.workflow_states import (
    INBOUND_DELIVERY_PROCESSED_STATES,
)


class FederationIntegrationDeliveryRetentionMixin(models.AbstractModel):
    _name = "federation.integration.delivery.retention.mixin"
    _description = "Federation Integration Delivery Retention Helpers"

    @api.model
    def _purge_retained_deliveries(self, reference_dt=None):
        """Delete terminal delivery records and payload attachments past retention."""
        reference_dt = fields.Datetime.to_datetime(
            reference_dt or fields.Datetime.now()
        )
        total_deleted = 0
        processed_states = set(INBOUND_DELIVERY_PROCESSED_STATES)
        for state, days in self.RETENTION_DAYS_BY_STATE.items():
            cutoff = fields.Datetime.to_string(reference_dt - timedelta(days=days))
            cutoff_field = (
                "processed_on" if state in processed_states else "received_on"
            )
            deliveries = self.sudo().search(
                [
                    ("state", "=", state),
                    (cutoff_field, "!=", False),
                    (cutoff_field, "<", cutoff),
                ]
            )
            attachments = deliveries.mapped("attachment_id").sudo()
            total_deleted += len(deliveries)
            attachments.unlink()
            deliveries.unlink()
        return total_deleted

    @api.model
    def _cron_purge_retained_deliveries(self):
        """Execute the inbound-delivery retention policy."""
        return self._purge_retained_deliveries()
