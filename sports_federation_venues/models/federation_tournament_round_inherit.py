from odoo import fields, models


class FederationTournamentRound(models.Model):
    _inherit = "federation.tournament.round"

    venue_id = fields.Many2one(
        "federation.venue",
        string="Venue",
    )

    def write(self, vals):
        """Update records with module-specific side effects."""
        sync_match_venues = "venue_id" in vals
        result = super().write(vals)
        if sync_match_venues:
            self._sync_match_venues_from_round()
        return result

    def _sync_match_venues_from_round(self):
        """Synchronize match venues from round."""
        for round_record in self.filtered(lambda rec: rec.venue_id):
            for match in round_record.match_ids:
                match_vals = {"venue_id": round_record.venue_id.id}
                if (
                    match.playing_area_id
                    and match.playing_area_id.venue_id != round_record.venue_id
                ):
                    match_vals["playing_area_id"] = False
                match.write(match_vals)
