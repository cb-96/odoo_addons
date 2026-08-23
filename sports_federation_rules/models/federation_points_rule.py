from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
