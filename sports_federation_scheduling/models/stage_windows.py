from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationStructureStageGameDays(models.Model):
    """Optional game days on which a competition stage may be played.

    Empty means any game day of its division. Use it to keep a regular
    season, a second half or a knockout on its own part of the calendar.
    """

    _inherit = "federation.structure.stage"

    matchday_ids = fields.Many2many(
        "federation.matchday",
        "federation_structure_stage_matchday_rel",
        "stage_id",
        "matchday_id",
        string="Game days",
        help="Only plan this stage on these game days. Leave empty to allow "
        "every game day where its division plays.",
    )

    @api.constrains("matchday_ids", "structure_id")
    def _check_stage_game_days(self):
        for stage in self:
            foreign = stage.matchday_ids.filtered(
                lambda day: day.edition_id != stage.structure_id.edition_id
            )
            if foreign:
                raise ValidationError(
                    _(
                        "%(stage)s can only use game days of its own competition.",
                        stage=stage.display_name,
                    )
                )
