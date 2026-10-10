from odoo import _, models
from odoo.exceptions import ValidationError


class FederationMatchdayLineup(models.Model):
    _inherit = "federation.matchday"

    def action_prepare_lineups(self):
        self.ensure_one()
        teams = (
            self.published_match_ids.mapped("home_team_id")
            | self.published_match_ids.mapped("away_team_id")
        )
        if not teams:
            raise ValidationError(
                _("Publish the schedule before preparing game-day lineups.")
            )
        wizard = self.env["federation.gameday.lineup.wizard"].create(
            {"matchday_id": self.id, "team_id": teams.sorted(lambda team: team.name)[:1].id}
        )
        wizard._onchange_team_id()
        return {
            "type": "ir.actions.act_window",
            "name": _("Prepare Game-Day Lineup"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
        }
