from odoo import fields, models


class FederationRuleSet(models.Model):
    _inherit = "federation.rule.set"

    club_duties_on_publication = fields.Boolean(
        string="Ask clubs for officials on publication",
        default=True,
        help=(
            "When a schedule is published, create one open club duty per required "
            "official (see Referees required per match) and share them fairly "
            "between the participating clubs, avoiding clubs that play at the same "
            "time. Turn this off when officials are assigned by the federation "
            "only. Existing duties and assignments are never duplicated."
        ),
    )
