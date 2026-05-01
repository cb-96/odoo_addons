from odoo import fields, models


class FederationImportWizardMixin(models.AbstractModel):
    _name = "federation.import.wizard.mixin"
    _description = "Federation Import Wizard Mixin"
    _inherit = [
        "federation.import.wizard.csv.mixin",
        "federation.import.wizard.governance.mixin",
    ]

    upload_file = fields.Binary(string="CSV File", required=True)
    upload_filename = fields.Char(string="Filename")
    dry_run = fields.Boolean(string="Dry Run", default=True)
    template_id = fields.Many2one(
        "federation.import.template",
        string="Import Template",
        default=lambda self: self._default_template_id(),
    )
    governance_job_id = fields.Many2one(
        "federation.import.job",
        string="Governance Job",
        readonly=True,
    )
    integration_delivery_id = fields.Many2one(
        "federation.integration.delivery",
        string="Inbound Delivery",
        readonly=True,
    )
    approval_state = fields.Selection(
        related="governance_job_id.state",
        string="Approval State",
        readonly=True,
    )
    contract_version = fields.Char(
        related="template_id.contract_version",
        string="Contract Version",
        readonly=True,
    )
    mapping_guide = fields.Text(
        string="Column Guide", compute="_compute_mapping_guide", readonly=True
    )
    result_message = fields.Text(string="Result", readonly=True)
    verification_summary = fields.Text(
        related="governance_job_id.verification_summary",
        string="Verification Summary",
        readonly=True,
    )
    line_count = fields.Integer(string="Total Lines", readonly=True)
    success_count = fields.Integer(string="Success", readonly=True)
    error_count = fields.Integer(string="Errors", readonly=True)
    preview_file_checksum = fields.Char(readonly=True)
