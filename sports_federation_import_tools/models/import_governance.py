from odoo import api, fields, models
from odoo.addons.sports_federation_base.models.failure_feedback import (
    FAILURE_CATEGORY_SELECTION,
)
from odoo.addons.sports_federation_import_tools.workflow_states import (
    IMPORT_JOB_REJECTABLE_STATES,
    IMPORT_JOB_RESUBMITTABLE_STATES,
    IMPORT_JOB_STATE_APPROVED,
    IMPORT_JOB_STATE_AWAITING_APPROVAL,
    IMPORT_JOB_STATE_REJECTED,
    IMPORT_JOB_STATE_SELECTION,
)
from odoo.exceptions import AccessError, ValidationError


class FederationImportTemplate(models.Model):
    _name = "federation.import.template"
    _description = "Federation Import Template"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    wizard_model = fields.Char(required=True)
    target_model = fields.Char(required=True)
    contract_version = fields.Char(required=True, default="csv_v1")
    required_columns_text = fields.Text()
    optional_columns_text = fields.Text()
    sample_header = fields.Char()
    notes = fields.Text()
    approval_required = fields.Boolean(default=True)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Import template codes must be unique.",
    )

    def build_mapping_guide(self):
        """Build mapping guide."""
        self.ensure_one()
        parts = [f"Template: {self.name} ({self.contract_version})"]
        if self.required_columns_text:
            parts.append(f"Required columns: {self.required_columns_text}")
        if self.optional_columns_text:
            parts.append(f"Optional columns: {self.optional_columns_text}")
        if self.sample_header:
            parts.append(f"Sample header: {self.sample_header}")
        if self.notes:
            parts.append(self.notes)
        return "\n".join(parts)


class FederationImportJob(models.Model):
    _name = "federation.import.job"
    _description = "Federation Import Governance Job"
    _order = "create_date desc, id desc"

    STATE_SELECTION = IMPORT_JOB_STATE_SELECTION

    name = fields.Char(required=True)
    template_id = fields.Many2one(
        "federation.import.template", required=True, ondelete="restrict"
    )
    wizard_model = fields.Char(required=True)
    target_model = fields.Char(required=True)
    state = fields.Selection(STATE_SELECTION, required=True, default="draft")
    contract_name = fields.Char(required=True)
    schema_version = fields.Char(required=True)
    upload_filename = fields.Char()
    integration_delivery_id = fields.Many2one(
        "federation.integration.delivery",
        ondelete="set null",
    )
    file_checksum = fields.Char(required=True)
    column_names = fields.Text()
    line_count = fields.Integer(readonly=True)
    success_count = fields.Integer(readonly=True)
    error_count = fields.Integer(readonly=True)
    failure_category = fields.Selection(FAILURE_CATEGORY_SELECTION, readonly=True)
    operator_message = fields.Text(readonly=True)
    preview_result_message = fields.Text(readonly=True)
    execution_result_message = fields.Text(readonly=True)
    verification_summary = fields.Text(readonly=True)
    requested_by_id = fields.Many2one("res.users", readonly=True)
    requested_on = fields.Datetime(readonly=True)
    approved_by_id = fields.Many2one("res.users", readonly=True)
    approved_on = fields.Datetime(readonly=True)
    rejected_by_id = fields.Many2one("res.users", readonly=True)
    rejected_on = fields.Datetime(readonly=True)
    rejection_reason = fields.Text()
    executed_by_id = fields.Many2one("res.users", readonly=True)
    executed_on = fields.Datetime(readonly=True)
    pre_import_record_count = fields.Integer(readonly=True)
    post_import_record_count = fields.Integer(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        Template = self.env["federation.import.template"]
        for vals in vals_list:
            if vals.get("name"):
                continue
            template = (
                Template.browse(vals.get("template_id"))
                if vals.get("template_id")
                else False
            )
            label = (
                template.name if template else vals.get("wizard_model") or "Import Job"
            )
            filename = vals.get("upload_filename") or "CSV Upload"
            vals["name"] = f"{label} - {filename}"
        return super().create(vals_list)

    def _require_manager(self):
        """Handle require manager."""
        if not self.env.user.has_group(
            "sports_federation_base.group_federation_manager"
        ):
            raise AccessError(
                "Only federation managers can approve or reject import jobs."
            )

    def action_submit_for_approval(self):
        """Execute the submit for approval action."""
        for record in self:
            if record.state not in IMPORT_JOB_RESUBMITTABLE_STATES:
                raise ValidationError(
                    "Only draft or rejected jobs can be submitted for approval."
                )
            record.write(
                {
                    "state": IMPORT_JOB_STATE_AWAITING_APPROVAL,
                    "requested_by_id": self.env.user.id,
                    "requested_on": fields.Datetime.now(),
                    "approved_by_id": False,
                    "approved_on": False,
                    "rejected_by_id": False,
                    "rejected_on": False,
                    "rejection_reason": False,
                    "failure_category": False,
                    "operator_message": False,
                }
            )
            if record.integration_delivery_id:
                record.integration_delivery_id.action_mark_awaiting_approval(record)

    def action_approve(self):
        """Execute the approve action."""
        self._require_manager()
        for record in self:
            if record.state != IMPORT_JOB_STATE_AWAITING_APPROVAL:
                raise ValidationError("Only jobs awaiting approval can be approved.")
            record.write(
                {
                    "state": IMPORT_JOB_STATE_APPROVED,
                    "approved_by_id": self.env.user.id,
                    "approved_on": fields.Datetime.now(),
                    "rejected_by_id": False,
                    "rejected_on": False,
                    "rejection_reason": False,
                    "failure_category": False,
                    "operator_message": False,
                }
            )
            if record.integration_delivery_id:
                record.integration_delivery_id.action_mark_approved(record)

    def action_reject(self):
        """Execute the reject action."""
        self._require_manager()
        for record in self:
            if record.state not in IMPORT_JOB_REJECTABLE_STATES:
                raise ValidationError("Only awaiting or approved jobs can be rejected.")
            record.write(
                {
                    "state": IMPORT_JOB_STATE_REJECTED,
                    "rejected_by_id": self.env.user.id,
                    "rejected_on": fields.Datetime.now(),
                    "approved_by_id": False,
                    "approved_on": False,
                    "failure_category": "operator_input",
                    "operator_message": record.rejection_reason
                    or "The governance job was rejected by a federation manager.",
                }
            )
            if record.integration_delivery_id:
                record.integration_delivery_id.action_mark_failed(
                    message=record.rejection_reason
                    or "The governance job was rejected.",
                    category="operator_input",
                    job=record,
                )
