from odoo import fields, models
from odoo.addons.sports_federation_base.models.failure_feedback import (
    DEFAULT_OPERATOR_MESSAGES,
)
from odoo.addons.sports_federation_import_tools.workflow_states import (
    IMPORT_JOB_STATE_COMPLETED,
    IMPORT_JOB_STATE_COMPLETED_WITH_ERRORS,
    is_import_job_approved,
)
from odoo.exceptions import AccessError, ValidationError


class FederationImportWizardGovernanceMixin(models.AbstractModel):
    _name = "federation.import.wizard.governance.mixin"
    _description = "Federation Import Wizard Governance Helpers"

    def _build_preview_verification_summary(self):
        """Build the dry-run summary persisted on the governance job."""
        self.ensure_one()
        return "\n".join(
            [
                f"Template: {self.template_id.display_name if self.template_id else self._name}",
                f"Contract version: {self.template_id.contract_version if self.template_id else 'n/a'}",
                f"Requested by: {self.env.user.display_name}",
                f"Preview totals: {self.line_count} lines, {self.success_count} successful, {self.error_count} errors",
                f"Current target record count: {self._get_target_record_count()}",
            ]
        )

    def _build_execution_verification_summary(self, baseline_count):
        """Build the live-run summary persisted on the governance job."""
        self.ensure_one()
        after_count = self._get_target_record_count()
        net_new = after_count - (baseline_count or 0)
        return "\n".join(
            [
                f"Template: {self.template_id.display_name if self.template_id else self._name}",
                f"Executed by: {self.env.user.display_name}",
                f"Execution totals: {self.line_count} lines, {self.success_count} successful, {self.error_count} errors",
                f"Target records before import: {baseline_count or 0}",
                f"Target records after import: {after_count}",
                f"Net new target records: {net_new}",
            ]
        )

    def _get_overall_failure_category(self, error_categories=None):
        """Return the top-level failure category for the latest import outcome."""
        categories = set((error_categories or {}).keys())
        if not (self.error_count or categories):
            return False
        if "unexpected_error" in categories:
            return "unexpected_bug"
        if self.error_count or categories:
            return "data_validation"
        return "operator_input"

    def _get_overall_operator_message(self, error_categories=None):
        """Return the operator-facing summary tied to the latest import outcome."""
        category = self._get_overall_failure_category(error_categories=error_categories)
        if not category:
            return False
        if category == "data_validation":
            return (
                "The import completed with row-level validation errors. Review the categorized result "
                "summary before retrying."
            )
        return DEFAULT_OPERATOR_MESSAGES[category]

    def _ensure_live_import_approved(self):
        """Verify that the current upload is still covered by an approval job."""
        self.ensure_one()
        if not self.template_id or not self.template_id.approval_required:
            return
        job = self.governance_job_id
        if not job or not is_import_job_approved(job.state):
            raise ValidationError(
                "Live imports require an approved governance job. Run a dry run, request approval, and approve the job before importing."
            )
        if job.file_checksum != self._current_upload_checksum():
            raise ValidationError(
                "The uploaded CSV has changed since approval. Run a fresh dry run and request approval again."
            )
        if job.template_id != self.template_id:
            raise ValidationError(
                "The selected import template does not match the approved governance job. Request approval again."
            )

    def _prepare_import_execution(self):
        """Return the baseline record count for live imports after approval checks."""
        self.ensure_one()
        if self.dry_run:
            return 0
        self._ensure_live_import_approved()
        return self._get_target_record_count()

    def _reopen_wizard(self):
        """Return the current wizard action to keep the modal open."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _finalize_import_result(
        self,
        line_count,
        success_count,
        error_count,
        errors,
        error_categories=None,
        baseline_count=0,
    ):
        """Persist wizard, governance, and inbound-delivery results in one place."""
        self.ensure_one()
        checksum = self._current_upload_checksum()
        result_message = self._build_result_message(
            line_count,
            success_count,
            error_count,
            errors,
            error_categories=error_categories,
        )
        write_vals = {
            "line_count": line_count,
            "success_count": success_count,
            "error_count": error_count,
            "result_message": result_message,
        }
        if self.dry_run:
            write_vals["preview_file_checksum"] = checksum
            if self.governance_job_id and (
                self.governance_job_id.file_checksum != checksum
                or self.governance_job_id.template_id != self.template_id
            ):
                write_vals["governance_job_id"] = False
        self.write(write_vals)

        if self.integration_delivery_id and self.dry_run:
            self.integration_delivery_id.action_mark_previewed(self)

        if (
            not self.dry_run
            and self.governance_job_id
            and is_import_job_approved(self.governance_job_id.state)
        ):
            after_count = self._get_target_record_count()
            failure_category = self._get_overall_failure_category(
                error_categories=error_categories
            )
            operator_message = self._get_overall_operator_message(
                error_categories=error_categories
            )
            self.governance_job_id.write(
                {
                    "state": (
                        IMPORT_JOB_STATE_COMPLETED
                        if not error_count
                        else IMPORT_JOB_STATE_COMPLETED_WITH_ERRORS
                    ),
                    "line_count": line_count,
                    "success_count": success_count,
                    "error_count": error_count,
                    "failure_category": failure_category,
                    "operator_message": operator_message,
                    "execution_result_message": result_message,
                    "verification_summary": self._build_execution_verification_summary(
                        baseline_count
                    ),
                    "pre_import_record_count": baseline_count,
                    "post_import_record_count": after_count,
                    "executed_by_id": self.env.user.id,
                    "executed_on": fields.Datetime.now(),
                }
            )
            if self.integration_delivery_id:
                self.integration_delivery_id.action_mark_processed(
                    self.governance_job_id
                )
        return self._reopen_wizard()

    def action_request_approval(self):
        """Create and submit the governance job for the current previewed upload."""
        self.ensure_one()
        if not self.template_id:
            raise ValidationError(
                "Select an import template before requesting approval."
            )
        current_checksum = self._current_upload_checksum()
        if (
            not self.preview_file_checksum
            or self.preview_file_checksum != current_checksum
        ):
            raise ValidationError(
                "Run a dry-run preview for the current CSV before requesting approval."
            )
        if not self.line_count:
            raise ValidationError("Run a dry-run preview before requesting approval.")

        columns = self._get_csv_reader().fieldnames or []
        job = self.env["federation.import.job"].create(
            {
                "template_id": self.template_id.id,
                "wizard_model": self._name,
                "target_model": self._get_import_target_model(),
                "state": "draft",
                "contract_name": self.template_id.code or self._name,
                "schema_version": self.template_id.contract_version or "csv_v1",
                "integration_delivery_id": self.integration_delivery_id.id,
                "upload_filename": self.upload_filename,
                "file_checksum": current_checksum,
                "column_names": ", ".join(columns),
                "line_count": self.line_count,
                "success_count": self.success_count,
                "error_count": self.error_count,
                "failure_category": self._get_overall_failure_category(),
                "operator_message": self._get_overall_operator_message(),
                "preview_result_message": self.result_message,
                "verification_summary": self._build_preview_verification_summary(),
            }
        )
        job.action_submit_for_approval()
        self.governance_job_id = job
        return self._reopen_wizard()

    def action_approve_import(self):
        """Approve the pending governance job for the current upload."""
        self.ensure_one()
        if not self.env.user.has_group(
            "sports_federation_base.group_federation_manager"
        ):
            raise AccessError("Only federation managers can approve import jobs.")
        if not self.governance_job_id:
            raise ValidationError("Request approval before approving an import job.")
        if self.governance_job_id.file_checksum != self._current_upload_checksum():
            raise ValidationError(
                "The uploaded CSV has changed since the approval request. Run a new dry run and request approval again."
            )
        self.governance_job_id.action_approve()
        return self._reopen_wizard()

    def action_view_governance_job(self):
        """Open the linked governance job in the current window."""
        self.ensure_one()
        if not self.governance_job_id:
            raise ValidationError("No governance job is linked to this import yet.")
        return {
            "type": "ir.actions.act_window",
            "name": "Import Governance Job",
            "res_model": "federation.import.job",
            "res_id": self.governance_job_id.id,
            "view_mode": "form",
            "target": "current",
        }
