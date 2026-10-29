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
        wizard_model = self.env["federation.gameday.lineup.wizard"]
        teams = teams.sorted(lambda item: (item.name or "", item.id))
        defaults_by_team = {
            team.id: wizard_model._lineup_defaults(self, team) for team in teams
        }
        team = next(
            (team for team in teams if defaults_by_team[team.id][0]),
            self.env["federation.team"],
        )
        if not team:
            raise ValidationError(
                _("Activate a team roster before preparing its game-day lineup.")
            )
        roster, lines = defaults_by_team[team.id]
        wizard = wizard_model.create(
            {
                "matchday_id": self.id,
                "team_id": team.id,
                "roster_id": roster.id,
                "line_ids": lines,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Prepare Game-Day Lineup"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
        }
