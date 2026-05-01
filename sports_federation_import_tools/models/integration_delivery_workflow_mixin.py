from odoo import fields, models
from odoo.addons.sports_federation_base.models.failure_feedback import (
    build_failure_feedback,
)
from odoo.addons.sports_federation_import_tools.workflow_states import (
    INBOUND_DELIVERY_STATE_APPROVED,
    INBOUND_DELIVERY_STATE_AWAITING_APPROVAL,
    INBOUND_DELIVERY_STATE_CANCELLED,
    INBOUND_DELIVERY_STATE_FAILED,
    delivery_state_from_job_state,
)
from odoo.exceptions import ValidationError


class FederationIntegrationDeliveryWorkflowMixin(models.AbstractModel):
    _name = "federation.integration.delivery.workflow.mixin"
    _description = "Federation Integration Delivery Workflow Helpers"

    def action_open_import_wizard(self):
        """Open the downstream import wizard for the staged payload."""
        self.ensure_one()
        if self.state == INBOUND_DELIVERY_STATE_CANCELLED:
            raise ValidationError(
                "Cancelled deliveries cannot be reopened in the import pipeline."
            )
        if not self.attachment_id or not self.attachment_id.datas:
            raise ValidationError(
                "The staged delivery does not have an attached payload."
            )
        if not self.import_template_id:
            raise ValidationError("This delivery is not linked to an import template.")

        wizard_model = self.import_template_id.wizard_model
        wizard_env = self.env.get(wizard_model)
        if wizard_env is None:
            raise ValidationError(
                "The import wizard for this delivery is not available."
            )

        wizard = wizard_env.create(
            {
                "template_id": self.import_template_id.id,
                "upload_file": self.attachment_id.datas,
                "upload_filename": self.filename,
                "dry_run": True,
                "integration_delivery_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Preview Partner Delivery",
            "res_model": wizard_model,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_cancel(self):
        """Cancel the inbound delivery."""
        self.write({"state": INBOUND_DELIVERY_STATE_CANCELLED})

    def action_mark_previewed(self, wizard):
        """Store the preview result on the delivery record."""
        wizard.ensure_one()
        self.ensure_one()
        self.write(
            {
                "state": "previewed",
                "previewed_on": fields.Datetime.now(),
                "line_count": wizard.line_count,
                "success_count": wizard.success_count,
                "error_count": wizard.error_count,
                "failure_category": wizard._get_overall_failure_category(),
                "operator_message": wizard._get_overall_operator_message(),
                "result_message": wizard.result_message,
            }
        )

    def action_mark_awaiting_approval(self, job):
        """Attach the awaiting-approval job state to the delivery."""
        job.ensure_one()
        self.ensure_one()
        self.write(
            {
                "state": INBOUND_DELIVERY_STATE_AWAITING_APPROVAL,
                "governance_job_id": job.id,
                "failure_category": job.failure_category,
                "operator_message": job.operator_message,
                "verification_summary": job.verification_summary,
            }
        )

    def action_mark_approved(self, job):
        """Attach the approved job state to the delivery."""
        job.ensure_one()
        self.ensure_one()
        self.write(
            {
                "state": INBOUND_DELIVERY_STATE_APPROVED,
                "governance_job_id": job.id,
                "approved_on": fields.Datetime.now(),
                "failure_category": False,
                "operator_message": False,
                "verification_summary": job.verification_summary,
            }
        )

    def action_mark_processed(self, job):
        """Persist final execution results back onto the delivery."""
        job.ensure_one()
        self.ensure_one()
        self.write(
            {
                "state": delivery_state_from_job_state(job.state),
                "governance_job_id": job.id,
                "processed_on": fields.Datetime.now(),
                "line_count": job.line_count,
                "success_count": job.success_count,
                "error_count": job.error_count,
                "failure_category": job.failure_category,
                "operator_message": job.operator_message,
                "result_message": job.execution_result_message
                or job.preview_result_message,
                "verification_summary": job.verification_summary,
            }
        )

    def action_mark_failed(self, message=None, category=None, job=None, error=None):
        """Persist a typed failure summary on the delivery."""
        self.ensure_one()
        failure_category, operator_message = build_failure_feedback(
            error=error,
            detail=message,
            default_category=category or "unexpected_bug",
        )
        values = {
            "state": INBOUND_DELIVERY_STATE_FAILED,
            "failure_category": failure_category,
            "operator_message": operator_message,
        }
        if operator_message:
            values["result_message"] = operator_message
        if job:
            values["governance_job_id"] = job.id
        self.write(values)
