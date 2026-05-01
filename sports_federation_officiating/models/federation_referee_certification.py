from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationRefereeCertification(models.Model):
    _name = "federation.referee.certification"
    _description = "Referee Certification"
    _order = "issue_date desc, id"

    name = fields.Char(string="Certification Number", required=True)
    referee_id = fields.Many2one(
        "federation.referee", string="Referee", required=True, ondelete="cascade"
    )
    level = fields.Selection(
        [
            ("local", "Local"),
            ("regional", "Regional"),
            ("national", "National"),
            ("international", "International"),
        ],
        string="Level",
        required=True,
    )
    issue_date = fields.Date(
        string="Issue Date", required=True, default=fields.Date.context_today
    )
    expiry_date = fields.Date(string="Expiry Date")
    issuing_body = fields.Char(string="Issuing Body")
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Notes")

    _referee_level_date_unique = models.Constraint(
        "unique (referee_id, level, issue_date)",
        "Duplicate certification for this referee, level, and date.",
    )

    @api.constrains("issue_date", "expiry_date")
    def _check_dates(self):
        """Validate dates."""
        for rec in self:
            if rec.issue_date and rec.expiry_date and rec.expiry_date <= rec.issue_date:
                raise ValidationError("Expiry date must be after issue date.")
