from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationTieBreakRule(models.Model):
    _name = "federation.tie_break.rule"
    _description = "Federation Tie-Break Rule"
    _order = "rule_set_id, sequence, id"

    rule_set_id = fields.Many2one(
        "federation.rule.set",
        string="Rule Set",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Sequence", default=10, required=True)
    tie_break_type = fields.Selection(
        [
            ("head_to_head", "Head-to-Head"),
            ("goal_difference", "Goal Difference"),
            ("goals_scored", "Goals Scored"),
            ("goals_against", "Goals Against (fewer)"),
            ("fair_play", "Fair Play"),
            ("drawing_of_lots", "Drawing of Lots"),
            ("ranking_points", "Ranking Points"),
            ("custom", "Custom"),
        ],
        string="Tie-Break Type",
        required=True,
    )
    description = fields.Char(
        string="Description",
        help="Optional description to clarify this tie-break rule.",
    )
    reverse_order = fields.Boolean(
        string="Reverse Order",
        default=False,
        help="If checked, lower values rank higher (e.g., fewer goals against).",
    )

    _rule_set_type_unique = models.Constraint(
        "UNIQUE(rule_set_id, tie_break_type)",
        "Each tie-break type can only appear once per rule set.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        rule_sets = self.env["federation.rule.set"].browse(
            [vals.get("rule_set_id") for vals in vals_list if vals.get("rule_set_id")]
        )
        if rule_sets.filtered("locked"):
            raise ValidationError("Locked rule sets cannot be changed.")
        return super().create(vals_list)

    def write(self, vals):
        if self.mapped("rule_set_id").filtered("locked"):
            raise ValidationError("Locked rule sets cannot be changed.")
        return super().write(vals)

    def unlink(self):
        if self.mapped("rule_set_id").filtered("locked"):
            raise ValidationError("Locked rule sets cannot be changed.")
        return super().unlink()
