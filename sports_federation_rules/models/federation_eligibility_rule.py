from odoo import fields, models


class FederationEligibilityRule(models.Model):
    _name = "federation.eligibility.rule"
    _description = "Federation Eligibility Rule"
    _order = "rule_set_id, sequence, id"

    rule_set_id = fields.Many2one(
        "federation.rule.set",
        string="Rule Set",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Sequence", default=10, required=True)
    name = fields.Char(string="Rule Name", required=True)
    eligibility_type = fields.Selection(
        [
            ("age_min", "Minimum Age"),
            ("age_max", "Maximum Age"),
            ("gender", "Gender / Category"),
            ("license_valid", "Valid License Required"),
            ("suspension", "No Active Suspension"),
            ("registration", "Registration Required"),
            ("custom", "Custom Rule"),
        ],
        string="Rule Type",
        required=True,
    )
    description = fields.Text(
        string="Description",
        help="Detailed description of this eligibility rule for reference.",
    )
    # Age-specific fields
    age_limit = fields.Integer(
        string="Age Limit",
        help="Age value for minimum/maximum age rules.",
    )
    # Gender/category
    allowed_categories = fields.Char(
        string="Allowed Categories",
        help="Comma-separated list of allowed categories (e.g., 'male,female,mixed').",
    )
    active = fields.Boolean(default=True)

    # Extension point marker
    is_placeholder = fields.Boolean(
        string="Placeholder Rule",
        default=False,
        help="Mark this rule as a placeholder for future implementation. "
        "Placeholder rules are not enforced but documented for planning.",
    )
