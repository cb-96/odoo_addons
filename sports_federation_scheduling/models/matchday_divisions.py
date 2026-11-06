"""Choose which divisions play on a game day.

Example: men's and women's divisions play on some game days, the mixed
division on the others.  An empty selection keeps the previous behaviour: all
divisions of the competition may be scheduled on the game day.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationMatchdayDivisions(models.Model):
    _inherit = "federation.matchday"

    division_ids = fields.Many2many(
        "federation.tournament",
        "federation_matchday_division_rel",
        "matchday_id",
        "division_id",
        string="Divisions playing",
        domain="[('edition_id', '=', edition_id)]",
        help="Only these divisions are scheduled on this game day. "
        "Leave empty to allow every division of the competition.",
    )

    @api.constrains("division_ids", "edition_id")
    def _check_division_scope(self):
        for day in self:
            foreign = day.division_ids.filtered(
                lambda division: division.edition_id != day.edition_id
            )
            if foreign:
                raise ValidationError(
                    _(
                        "%(day)s: only divisions of this competition can play on it.",
                        day=day.display_name,
                    )
                )

    def _allows_division(self, division):
        self.ensure_one()
        return not self.division_ids or division in self.division_ids
