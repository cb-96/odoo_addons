from odoo import api, fields, models


class FederationComplianceCheckArchive(models.Model):
    _name = "federation.compliance.check.archive"
    _description = "Federation Compliance Check Archive"
    _order = "archived_on desc, id desc"

    STATUS_SELECTION = [
        ("compliant", "Compliant"),
        ("missing", "Missing"),
        ("pending", "Pending"),
        ("expired", "Expired"),
        ("non_compliant", "Non Compliant"),
    ]

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    compliance_check_id = fields.Many2one(
        "federation.compliance.check",
        string="Compliance Check",
        ondelete="set null",
        index=True,
    )
    archived_on = fields.Datetime(
        string="Archived On", required=True, default=fields.Datetime.now, index=True
    )
    checked_on = fields.Datetime(string="Checked On")
    target_model = fields.Char(string="Target Model", required=True, index=True)
    target_res_id = fields.Integer(string="Target Record ID", required=True, index=True)
    target_display = fields.Char(string="Target", required=True)
    requirement_id = fields.Many2one(
        "federation.document.requirement",
        string="Requirement",
        ondelete="set null",
        index=True,
    )
    submission_id = fields.Many2one(
        "federation.document.submission",
        string="Submission",
        ondelete="set null",
    )
    status = fields.Selection(
        selection=STATUS_SELECTION, string="Status", required=True, index=True
    )
    note = fields.Char(string="Note")

    @api.depends("target_display", "status", "archived_on")
    def _compute_name(self):
        """Compute name."""
        labels = dict(self._fields["status"].selection)
        for record in self:
            status_label = labels.get(record.status, record.status or "Archive")
            record.name = (
                f"{record.target_display} - {status_label} - {record.archived_on}"
                if record.archived_on
                else f"{record.target_display} - {status_label}"
            )
