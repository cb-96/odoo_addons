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
    def _retention_candidates(self, reference_dt=None):
        reference_dt = fields.Datetime.to_datetime(
            reference_dt or fields.Datetime.now()
        )
        processed_states = set(INBOUND_DELIVERY_PROCESSED_STATES)
        candidates = self.browse()
        for state, days in self.RETENTION_DAYS_BY_STATE.items():
            field = "processed_on" if state in processed_states else "received_on"
            candidates |= self.sudo().search(
                [
                    ("state", "=", state),
                    (field, "!=", False),
                    (
                        field,
                        "<",
                        fields.Datetime.to_string(reference_dt - timedelta(days=days)),
                    ),
                ]
            )
        return candidates

    @api.model
    def _cron_purge_retained_deliveries(self):
        started_on = fields.Datetime.now()
        candidates = self._retention_candidates(started_on)
        attachments = len(candidates.mapped("attachment_id"))
        Evidence = self.env["federation.retention.evidence"]
        try:
            deleted = self._purge_retained_deliveries(started_on)
        except Exception as error:
            Evidence.record_failure_durable(
                "integration_deliveries",
                started_on=started_on,
                candidate_count=len(candidates),
                attachment_count=attachments,
                failure_count=len(candidates) or 1,
                retention_rules=self.RETENTION_DAYS_BY_STATE,
                operator_message=str(error),
                source_model=self._name,
            )
            raise
        Evidence.record_execution(
            "integration_deliveries",
            started_on=started_on,
            candidate_count=len(candidates),
            deleted_count=deleted,
            skipped_count=max(0, len(candidates) - deleted),
            attachment_count=attachments,
            retention_rules=self.RETENTION_DAYS_BY_STATE,
            source_model=self._name,
        )
        return deleted
