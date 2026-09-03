from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionFormatTemplate(models.Model):
    _name = "federation.competition.format.template"
    _description = "Versioned Competition Format Template"
    _order = "code, version desc, id desc"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    version = fields.Integer(default=1, required=True)
    active = fields.Boolean(default=True)
    format_type = fields.Selection(
        [
            ("single_round_robin", "League"),
            ("double_round_robin", "Double League"),
            ("knockout", "Knockout Cup"),
            ("pool_knockout", "Pools then Knockout"),
            ("split_pools", "Championship/Relegation Pools"),
            ("placement_bracket", "Placement Bracket"),
            ("swiss", "Swiss"),
            ("double_elimination", "Double Elimination"),
            ("ladder", "Challenge Ladder"),
        ],
        required=True,
    )
    pool_count = fields.Integer(default=2, required=True)
    series_length = fields.Selection(
        [
            ("1", "Single match"),
            ("3", "Best of 3"),
            ("5", "Best of 5"),
            ("7", "Best of 7"),
        ],
        default="1",
        required=True,
    )
    swiss_round_count = fields.Integer(default=5)
    configuration = fields.Json(default=dict)
    notes = fields.Text()

    _unique_code_version = models.Constraint(
        "unique(code, version)", "Template code and version must be unique."
    )

    @api.constrains("version", "pool_count", "swiss_round_count")
    def _check_positive_values(self):
        for template in self:
            if (
                template.version < 1
                or template.pool_count < 1
                or template.swiss_round_count < 1
            ):
                raise ValidationError(
                    "Template version and format counts must be positive."
                )

    def action_create_structure(self, edition, division, participant_set):
        self.ensure_one()
        return self.env["federation.competition.structure"].create(
            {
                "name": f"{edition.display_name} - {self.name} v{self.version}",
                "edition_id": edition.id,
                "division_id": division.id,
                "participant_set_id": participant_set.id,
                "format_type": self.format_type,
                "pool_count": self.pool_count,
                "series_length": self.series_length,
                "template_id": self.id,
            }
        )


class FederationCompetitionStructureTemplate(models.Model):
    _inherit = "federation.competition.structure"

    template_id = fields.Many2one(
        "federation.competition.format.template", readonly=True, ondelete="restrict"
    )
