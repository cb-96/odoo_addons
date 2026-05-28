from odoo import fields, models


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
