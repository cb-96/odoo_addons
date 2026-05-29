from odoo import models


class FederationSeasonRegistration(models.Model):
    _inherit = "federation.season.registration"

    def action_open_team_rosters(self):
        """Open the roster workspace that follows this season registration."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_rosters.action_federation_team_roster"
        )
        domain = []
        context = {}
        if self.team_id:
            domain.append(("team_id", "=", self.team_id.id))
            context["default_team_id"] = self.team_id.id
        if self.season_id:
            domain.append(("season_id", "=", self.season_id.id))
            context["default_season_id"] = self.season_id.id
        if getattr(self, "competition_id", False):
            domain.append(("competition_id", "=", self.competition_id.id))
            context["default_competition_id"] = self.competition_id.id
        if getattr(self, "rule_set_id", False):
            context["default_rule_set_id"] = self.rule_set_id.id
        context["default_season_registration_id"] = self.id

        roster = self.env["federation.team.roster"].search(domain, limit=1)
        if roster:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": roster.id,
                    "domain": [],
                }
            )
        else:
            action["domain"] = domain
        action["context"] = context
        return action
