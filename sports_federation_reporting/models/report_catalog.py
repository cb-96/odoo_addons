from odoo import fields, models


class FederationReportCatalog(models.Model):
    _name = "federation.report.catalog"
    _description = "Report Catalog"
    _order = "category, name"

    name = fields.Char(required=True, translate=True)
    technical_model = fields.Char(required=True, index=True)
    category = fields.Selection(
        [
            ("operations", "Operations"),
            ("competition", "Competition"),
            ("people", "People and Officiating"),
            ("assurance", "Assurance"),
            ("finance", "Finance"),
            ("audit", "Audit"),
        ],
        required=True,
        index=True,
    )
    purpose = fields.Text(required=True, translate=True)
    owner = fields.Char(required=True)
    requirement = fields.Selection(
        [
            ("operational", "Operationally required"),
            ("governance", "Governance or legal requirement"),
            ("active", "Optional and actively used"),
            ("review", "Usage must be confirmed"),
            ("retire", "Retire"),
        ],
        required=True,
        default="review",
        index=True,
    )
    active = fields.Boolean(default=True)
    last_confirmed_on = fields.Date()

    _technical_model_unique = models.Constraint(
        "UNIQUE(technical_model)",
        "A reporting model can occur only once in the report catalog.",
    )
