from odoo import _, models
from odoo.exceptions import ValidationError


class FederationIntegrationDeliveryJobReliability(models.Model):
    _inherit = "federation.integration.delivery"

    def action_create_recovery_job(self):
        for delivery in self:
            if delivery.state != "failed":
                raise ValidationError(_("Only failed deliveries need recovery."))
            job = self.env["federation.operation.job"].ensure_job(
                delivery,
                delivery.idempotency_key or f"delivery-{delivery.id}",
                name=f"Recover inbound delivery: {delivery.filename}",
                max_attempts=1,
            )
            if job.state == "pending":
                job._start()
                job._fail(
                    _(
                        "Open the source delivery, correct its governance or payload issue, then replay it through the import wizard."
                    ),
                    "operator_action",
                    retryable=False,
                )
        return True

    def _retry_operational_job(self, job):
        raise ValidationError(
            _(
                "Inbound deliveries require operator review and replay through the import wizard."
            )
        )
