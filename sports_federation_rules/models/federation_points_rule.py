from odoo import fields, models


class FederationPointsRule(models.Model):
    _name = "federation.points.rule"
    _description = "Federation Points Rule"
    _order = "result_type"

    rule_set_id = fields.Many2one(
        "federation.rule.set",
        string="Rule Set",
        required=True,
        ondelete="cascade",
    )
    result_type = fields.Selection(
        [
            ("win", "Win"),
            ("draw", "Draw"),
            ("loss", "Loss"),
            ("bye", "Bye"),
            ("forfeit_win", "Forfeit Win"),
            ("forfeit_loss", "Forfeit Loss"),
        ],
        string="Result Type",
        required=True,
    )
    points = fields.Integer(
        string="Points",
        required=True,
        default=0,
        help="Points awarded for this result type.",
    )

    _rule_set_result_unique = models.Constraint(
        "UNIQUE(rule_set_id, result_type)",
        "Each result type can only appear once per rule set.",
    )
