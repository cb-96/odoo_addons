from odoo import fields, models


class FederationPlayer(models.Model):
    _inherit = "federation.player"

    roster_line_ids = fields.One2many(
        "federation.team.roster.line",
        "player_id",
        string="Roster Lines",
    )
    match_sheet_line_ids = fields.One2many(
        "federation.match.sheet.line",
        "player_id",
        string="Match Sheet Lines",
    )
