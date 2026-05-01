from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationMatch(models.Model):
    _inherit = "federation.match"

    venue_id = fields.Many2one(
        "federation.venue",
        string="Venue",
        tracking=True,
    )
    playing_area_id = fields.Many2one(
        "federation.playing.area",
        string="Playing Area",
        domain="[('venue_id', '=', venue_id)]",
        tracking=True,
    )

    def _apply_round_venue_defaults(self, vals):
        """Apply round venue defaults."""
        round_id = vals.get("round_id")
        if not round_id:
            return vals

        round_record = self.env["federation.tournament.round"].browse(round_id)
        if not round_record.exists():
            return vals

        if round_record.venue_id and not vals.get("venue_id"):
            vals["venue_id"] = round_record.venue_id.id
        if vals.get("playing_area_id") and vals.get("venue_id"):
            playing_area = self.env["federation.playing.area"].browse(
                vals["playing_area_id"]
            )
            if playing_area.exists() and playing_area.venue_id.id != vals["venue_id"]:
                vals["playing_area_id"] = False
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        prepared_vals_list = [
            self._apply_round_venue_defaults(dict(vals)) for vals in vals_list
        ]
        return super().create(prepared_vals_list)

    def write(self, vals):
        """Update records with module-specific side effects."""
        prepared_vals = self._apply_round_venue_defaults(dict(vals))
        return super().write(prepared_vals)

    @api.constrains("venue_id", "playing_area_id")
    def _check_playing_area_venue(self):
        """Validate playing area venue."""
        for rec in self:
            if rec.playing_area_id and rec.venue_id:
                if rec.playing_area_id.venue_id != rec.venue_id:
                    raise ValidationError(
                        "The playing area must belong to the selected venue."
                    )

    @api.onchange("playing_area_id")
    def _onchange_playing_area_id(self):
        """Handle onchange playing area ID."""
        if self.playing_area_id and not self.venue_id:
            self.venue_id = self.playing_area_id.venue_id

    @api.onchange("round_id")
    def _onchange_round_id(self):
        """Handle onchange round ID."""
        super()._onchange_round_id()
        if not self.round_id:
            return
        if self.round_id.venue_id:
            self.venue_id = self.round_id.venue_id
        if (
            self.playing_area_id
            and self.venue_id
            and self.playing_area_id.venue_id != self.venue_id
        ):
            self.playing_area_id = False

    @api.constrains("round_id", "venue_id")
    def _check_round_venue_scope(self):
        """Validate round venue scope."""
        for rec in self:
            if not rec.round_id:
                continue
            if rec.round_id.venue_id and rec.round_id.venue_id != rec.venue_id:
                raise ValidationError(
                    _("A match venue must match the selected round venue.")
                )

    @api.constrains("round_id", "home_team_id", "away_team_id")
    def _check_no_duplicate_pairings_in_round(self):
        """Validate no duplicate pairings in round."""
        for rec in self:
            if not rec.round_id or not rec.home_team_id or not rec.away_team_id:
                continue
            # Only enforce when teams belong to the same category
            if rec.home_team_id.category != rec.away_team_id.category:
                continue
            domain = [
                ("round_id", "=", rec.round_id.id),
                "|",
                "&",
                ("home_team_id", "=", rec.home_team_id.id),
                ("away_team_id", "=", rec.away_team_id.id),
                "&",
                ("home_team_id", "=", rec.away_team_id.id),
                ("away_team_id", "=", rec.home_team_id.id),
                ("id", "!=", rec.id),
            ]
            dup = self.search(domain, limit=1)
            if dup:
                raise ValidationError(
                    "Teams in the same category cannot play the same opponent more than once in the same round."
                )
