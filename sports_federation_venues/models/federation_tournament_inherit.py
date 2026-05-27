from odoo import fields, models


class FederationTournament(models.Model):
    _inherit = "federation.tournament"

    venue_id = fields.Many2one(
        "federation.venue",
        string="Venue",
        tracking=True,
    )
    venue_notes = fields.Text(string="Venue Notes")
    required_playing_area_capability_ids = fields.Many2many(
        "federation.playing.area.capability",
        "federation_tournament_playing_area_capability_rel",
        "tournament_id",
        "capability_id",
        string="Required Court Capabilities",
        help="Matches from this division should only be assigned onto courts that provide these capabilities.",
    )
