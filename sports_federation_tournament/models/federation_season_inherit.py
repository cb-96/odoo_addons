from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationSeason(models.Model):
    _inherit = "federation.season"

    tournament_ids = fields.One2many(
        "federation.tournament",
        "season_id",
        string="Tournaments",
    )
    tournament_count = fields.Integer(
        string="Tournament Count",
        compute="_compute_tournament_count",
    )

    @api.depends("tournament_ids")
    def _compute_tournament_count(self):
        """Compute tournament count."""
        for record in self:
            record.tournament_count = len(record.tournament_ids)

    def action_view_tournaments(self):
        """Open the related tournaments."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Tournaments",
            "res_model": "federation.tournament",
            "view_mode": "list,form",
            "domain": [("season_id", "=", self.id)],
        }

    def action_close(self):
        """Block season closure if any linked tournament is still active."""
        for season in self:
            blocking = season.tournament_ids.filtered(
                lambda t: t.state not in ("closed", "cancelled")
            )
            if blocking:
                names = ", ".join(blocking.mapped("name")[:5])
                suffix = "…" if len(blocking) > 5 else ""
                raise ValidationError(
                    _(
                        "Cannot close season '%(season)s': %(count)d tournament(s) "
                        "are still active (%(names)s%(suffix)s). Close or cancel all "
                        "tournaments before closing the season.",
                        season=season.name,
                        count=len(blocking),
                        names=names,
                        suffix=suffix,
                    )
                )
        return super().action_close()
