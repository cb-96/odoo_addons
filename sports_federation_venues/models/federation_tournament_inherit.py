from odoo import fields, models


class FederationTournament(models.Model):
    _inherit = "federation.tournament"

    venue_id = fields.Many2one(
        "federation.venue",
        string="Venue",
        tracking=True,
    )
    venue_notes = fields.Text(string="Venue Notes")
