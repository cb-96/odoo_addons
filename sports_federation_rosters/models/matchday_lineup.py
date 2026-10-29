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
        self.check_access("read")
        matches = self.published_match_ids.filtered(lambda m: m.state not in ("done", "cancelled"))
        sheets = self.env["federation.match.sheet"].search([("match_id", "in", matches.ids)])
        approved = {(s.match_id.id, s.team_id.id) for s in sheets if s.state in ("approved", "locked")}
        pending_teams = teams.filtered(lambda t: any(
            t in (m.home_team_id | m.away_team_id) and (m.id, t.id) not in approved for m in matches
        )).sorted(lambda t: (t.name or "", t.id))
        if not pending_teams:
            raise ValidationError(_("All current lineups are already approved."))
        defaults = {t.id: wizard_model._lineup_defaults(self, t) for t in pending_teams}
        team = next((t for t in pending_teams if defaults[t.id][0]), pending_teams[:1])
        submitted = sheets.filtered(lambda s: s.team_id == team and s.state == "submitted")[:1]
        if submitted:
            return submitted.get_formview_action()
        roster, lines = defaults[team.id]
        if not roster:
            division = matches.filtered(lambda m: team in (m.home_team_id | m.away_team_id))[:1].tournament_id
            return team._ensure_tournament_roster(division).get_formview_action()
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
