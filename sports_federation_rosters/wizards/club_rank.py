from odoo import _, api, fields, models


class FederationGamedayLineupWizardClubRank(models.TransientModel):
    _inherit = "federation.gameday.lineup.wizard"

    club_rank_warning = fields.Text(
        string="Team promotion warning",
        compute="_compute_club_rank_warning",
    )

    @api.depends("team_id", "roster_id", "matchday_id", "line_ids.player_id")
    def _compute_club_rank_warning(self):
        service = self.env["federation.club.rank.service"]
        for wizard in self:
            matches = wizard.matchday_id.published_match_ids.filtered(
                lambda match: wizard.team_id
                in (match.home_team_id | match.away_team_id)
                and match.state not in ("done", "cancelled")
            )
            warnings = service.promotion_warnings(
                wizard.roster_id, wizard.line_ids.player_id, len(matches)
            )
            wizard.club_rank_warning = "\n".join(warnings) or False
